"""Unit tests for framework/confirmations/* modules.

Every confirmation pattern has >= 10 synthetic test cases covering:
- canonical valid signal
- valid rejection (pattern absent)
- ambiguous / near-miss cases (e.g. body_ratio at 0.105)
- edge cases: zero range, NaN OHLCV, missing prior bars

All synthetic data — never pulls real bars.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from framework.confirmations import (
    Acceptance,
    BreakoutCandle,
    L2Confirm,
    Rejection,
    SignalCandle,
    VolumeConfirm,
)
from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


# ---------------------------------------------------------------------------
# Helpers — synthetic bar / level builders.
# ---------------------------------------------------------------------------

BASE_TS = datetime(2026, 5, 17, 14, 30, tzinfo=timezone.utc)


def mk_bar(
    *,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1000.0,
    offset_min: int = 0,
    symbol: str = "TEST",
) -> Bar:
    """Build a Bar with simple defaults."""
    return Bar(
        timestamp=BASE_TS + timedelta(minutes=offset_min),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        symbol=symbol,
    )


def mk_series(n: int, base_vol: float = 1000.0, base_close: float = 10.0) -> list[Bar]:
    """Build n flat bars for use as 'prior' history."""
    return [
        mk_bar(
            open=base_close,
            high=base_close + 0.05,
            low=base_close - 0.05,
            close=base_close,
            volume=base_vol,
            offset_min=i,
        )
        for i in range(n)
    ]


def mk_level(price: float, kind: str = "PDH") -> Level:
    return Level(price=price, kind=kind, session_date=date(2026, 5, 17))


# Reference candles for signal_candle tests.

def canonical_doji() -> Bar:
    """body / range = 0 / 1.0 = 0.0 -> doji. Volume above prior."""
    return mk_bar(open=10.00, high=10.50, low=9.50, close=10.00, volume=2000, offset_min=1)


def canonical_hammer() -> Bar:
    """Long lower wick, small (non-doji) body in upper part of range.

    range=1.00, body=0.15 (body_ratio=0.15, in [0.10, 0.30) so NOT a doji
    but still hammer). Body in upper 30% of range. Lower wick = 0.75
    (> 2 * body = 0.30).
    """
    return mk_bar(open=10.80, high=10.95, low=10.00, close=10.95, volume=2000, offset_min=1)


def canonical_shooting_star() -> Bar:
    """Long upper wick, small (non-doji) body in lower part of range.

    range=1.00, body=0.15 (body_ratio=0.15, hammer/shooting-star band).
    Body in lower 30% of range. Upper wick = 0.75 (> 2 * body = 0.30).
    """
    return mk_bar(open=10.00, high=10.95, low=10.00, close=10.15, volume=2000, offset_min=1)


def prior_bar_for_volume(vol: float = 1000.0) -> Bar:
    return mk_bar(open=10.0, high=10.1, low=9.9, close=10.0, volume=vol, offset_min=0)


# ---------------------------------------------------------------------------
# SignalCandle — >= 10 cases
# ---------------------------------------------------------------------------

class TestSignalCandle:
    def test_canonical_doji_detected(self):
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), canonical_doji()])
        assert result.confirmed
        assert result.pattern_name == "doji"

    def test_canonical_hammer_detected(self):
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), canonical_hammer()])
        assert result.confirmed
        assert result.pattern_name == "hammer"

    def test_canonical_shooting_star_detected(self):
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), canonical_shooting_star()])
        assert result.confirmed
        assert result.pattern_name == "shooting_star"

    def test_volume_decrease_rejects(self):
        """Even a perfect doji is rejected if volume doesn't increase."""
        sc = SignalCandle(require_volume_increase=True)
        doji = canonical_doji()
        prior = prior_bar_for_volume(vol=5000)  # higher than doji's 2000
        result = sc.check_confirmation(mk_level(10.0), [prior, doji])
        assert not result.confirmed
        assert "volume not increasing" in result.reason

    def test_volume_check_disabled(self):
        """With require_volume_increase=False, volume is irrelevant."""
        sc = SignalCandle(require_volume_increase=False)
        doji = mk_bar(open=10.00, high=10.50, low=9.50, close=10.00, volume=500, offset_min=1)
        prior = prior_bar_for_volume(vol=5000)
        result = sc.check_confirmation(mk_level(10.0), [prior, doji])
        assert result.confirmed
        assert result.pattern_name == "doji"

    def test_body_ratio_just_below_threshold_doji(self):
        """body_ratio = 0.095 (< 0.10) -> doji."""
        # range = 1.0, body = 0.095 -> just barely doji
        bar = mk_bar(open=10.00, high=10.50, low=9.50, close=10.095, volume=2000, offset_min=1)
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        # body_ratio = 0.095/1.0 = 0.095 < 0.10 -> doji
        assert result.confirmed
        assert result.pattern_name == "doji"

    def test_body_ratio_at_0_105_rejects_doji(self):
        """body_ratio = 0.105 (> 0.10) -> NOT a doji.

        Per the directive's exact criteria. Should also fail hammer/shooting_star
        because we don't have appropriate wick structure.
        """
        # range = 1.0, body = 0.105
        bar = mk_bar(open=10.00, high=10.50, low=9.50, close=10.105, volume=2000, offset_min=1)
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert not result.confirmed

    def test_zero_range_rejects(self):
        """Open == high == low == close -> range 0."""
        bar = mk_bar(open=10.0, high=10.0, low=10.0, close=10.0, volume=2000, offset_min=1)
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert not result.confirmed
        assert "zero range" in result.reason

    def test_empty_bars_rejects(self):
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [])
        assert not result.confirmed
        assert "no bars" in result.reason

    def test_missing_prior_bar_with_volume_check(self):
        sc = SignalCandle(require_volume_increase=True)
        result = sc.check_confirmation(mk_level(10.0), [canonical_doji()])
        assert not result.confirmed
        assert "no prior bar" in result.reason

    def test_nan_open_rejects(self):
        bar = mk_bar(open=float("nan"), high=10.5, low=9.5, close=10.0, volume=2000, offset_min=1)
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert not result.confirmed
        assert "nan" in result.reason.lower()

    def test_nan_volume_rejects(self):
        bar = mk_bar(open=10.0, high=10.5, low=9.5, close=10.0, volume=float("nan"), offset_min=1)
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert not result.confirmed
        assert "nan" in result.reason.lower()

    def test_hammer_misses_when_body_in_lower_half(self):
        """Body in lower half disqualifies hammer (otherwise it'd be a shooting_star analog)."""
        # range = 1.0, body = 0.05, body at low end -> not hammer
        bar = mk_bar(open=10.00, high=10.95, low=10.00, close=10.05, volume=2000, offset_min=1)
        # bar.lower_wick = 0, upper_wick = 0.90. This is a shooting_star, NOT a hammer.
        sc = SignalCandle(patterns=["hammer"])
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert not result.confirmed

    def test_shooting_star_misses_when_body_in_upper_half(self):
        bar = canonical_hammer()  # body in upper -> not shooting_star
        sc = SignalCandle(patterns=["shooting_star"])
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert not result.confirmed

    def test_invalid_pattern_name_raises(self):
        with pytest.raises(ValueError):
            SignalCandle(patterns=["nonsense_pattern"])

    def test_pattern_priority_doji_before_hammer(self):
        """A bar that satisfies both doji & hammer returns doji (configured first)."""
        # Tiny body in upper area with long lower wick.
        # range = 1.0, body = 0.01 (body_ratio = 0.01 -> doji),
        # body in upper 0.99-1.0 of range, lower_wick = 0.99 (> 2*body=0.02)
        bar = mk_bar(open=10.99, high=11.00, low=10.00, close=11.00, volume=2000, offset_min=1)
        sc = SignalCandle(patterns=["doji", "hammer", "shooting_star"])
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), bar])
        assert result.confirmed
        assert result.pattern_name == "doji"

    def test_strength_clamped_to_unit_interval(self):
        sc = SignalCandle()
        result = sc.check_confirmation(mk_level(10.0), [prior_bar_for_volume(), canonical_doji()])
        assert 0.0 <= result.strength <= 1.0


# ---------------------------------------------------------------------------
# BreakoutCandle — >= 10 cases
# ---------------------------------------------------------------------------

class TestBreakoutCandle:
    def _hist(self, n: int = 20, vol: float = 1000.0) -> list[Bar]:
        return mk_series(n=n, base_vol=vol)

    def test_long_breakout_with_volume(self):
        bc = BreakoutCandle(min_vol_mult=2.0, min_breakout_pct=0.0002)
        level = mk_level(10.0, kind="PDH")
        # close = 10.05 > 10.002, vol = 5000 > 2x baseline 1000
        entry = mk_bar(open=10.0, high=10.10, low=9.99, close=10.05, volume=5000, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert result.confirmed
        assert result.pattern_name == "breakout_candle"
        assert result.metadata["direction"] == "long"

    def test_long_breakout_fails_no_close_beyond(self):
        bc = BreakoutCandle(min_vol_mult=2.0)
        level = mk_level(10.0, kind="PDH")
        entry = mk_bar(open=10.0, high=10.20, low=9.99, close=9.99, volume=5000, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert not result.confirmed
        assert "no breakout" in result.reason

    def test_long_breakout_fails_volume(self):
        bc = BreakoutCandle(min_vol_mult=3.0)
        level = mk_level(10.0, kind="PDH")
        entry = mk_bar(open=10.0, high=10.10, low=9.99, close=10.05, volume=1500, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert not result.confirmed
        assert "vol_mult" in result.reason

    def test_short_breakout_with_volume(self):
        bc = BreakoutCandle(min_vol_mult=2.0)
        level = mk_level(10.0, kind="PDL")  # support -> short on break-down
        entry = mk_bar(open=10.0, high=10.01, low=9.85, close=9.90, volume=5000, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert result.confirmed
        assert result.metadata["direction"] == "short"

    def test_explicit_direction_override(self):
        bc = BreakoutCandle(min_vol_mult=2.0, direction="short")
        # Even though level kind is PDH, force short
        level = mk_level(10.0, kind="PDH")
        entry = mk_bar(open=10.0, high=10.01, low=9.85, close=9.90, volume=5000, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert result.confirmed
        assert result.metadata["direction"] == "short"

    def test_breakout_wick_not_close(self):
        """require_close_beyond=False -> high triggers."""
        bc = BreakoutCandle(min_vol_mult=2.0, require_close_beyond=False)
        level = mk_level(10.0, kind="PDH")
        entry = mk_bar(open=9.95, high=10.10, low=9.94, close=9.99, volume=5000, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert result.confirmed

    def test_no_level_rejects(self):
        bc = BreakoutCandle()
        result = bc.check_confirmation(None, [mk_bar(open=10, high=10, low=10, close=10)])
        assert not result.confirmed
        assert "no level" in result.reason

    def test_no_bars_rejects(self):
        bc = BreakoutCandle()
        result = bc.check_confirmation(mk_level(10.0), [])
        assert not result.confirmed
        assert "no bars" in result.reason

    def test_nan_close_rejects(self):
        bc = BreakoutCandle(min_vol_mult=2.0)
        entry = mk_bar(open=10.0, high=10.1, low=9.9, close=float("nan"), volume=5000, offset_min=21)
        result = bc.check_confirmation(mk_level(10.0, "PDH"), self._hist() + [entry])
        assert not result.confirmed
        assert "nan" in result.reason.lower()

    def test_no_volume_baseline_rejects(self):
        bc = BreakoutCandle(min_vol_mult=2.0)
        # Only entry bar, no prior history -> no baseline
        entry = mk_bar(open=10.0, high=10.1, low=9.99, close=10.05, volume=5000, offset_min=0)
        result = bc.check_confirmation(mk_level(10.0, "PDH"), [entry])
        assert not result.confirmed
        assert "baseline" in result.reason

    def test_zero_baseline_volume_rejects(self):
        bc = BreakoutCandle(min_vol_mult=2.0)
        hist = mk_series(n=5, base_vol=0.0)
        entry = mk_bar(open=10.0, high=10.10, low=9.99, close=10.05, volume=5000, offset_min=6)
        result = bc.check_confirmation(mk_level(10.0, "PDH"), hist + [entry])
        assert not result.confirmed

    def test_invalid_level_price(self):
        bc = BreakoutCandle()
        level = Level(price=0.0, kind="PDH", session_date=date(2026, 5, 17))
        entry = mk_bar(open=10.0, high=10.1, low=9.9, close=10.05, volume=5000, offset_min=21)
        result = bc.check_confirmation(level, self._hist() + [entry])
        assert not result.confirmed
        assert "invalid level" in result.reason

    def test_breakout_pct_threshold(self):
        """0.0002 = 2bps; level=100 -> threshold 100.02."""
        bc = BreakoutCandle(min_vol_mult=2.0, min_breakout_pct=0.0002)
        level = mk_level(100.0, kind="ROUND")
        # close = 100.01 -> not over threshold; close = 100.03 -> over
        hist = mk_series(n=20, base_vol=1000, base_close=99.0)
        near = mk_bar(open=99.0, high=100.05, low=99.0, close=100.01, volume=5000, offset_min=21)
        over = mk_bar(open=99.0, high=100.05, low=99.0, close=100.03, volume=5000, offset_min=21)
        assert not bc.check_confirmation(level, hist + [near]).confirmed
        assert bc.check_confirmation(level, hist + [over]).confirmed


# ---------------------------------------------------------------------------
# Acceptance — >= 10 cases
# ---------------------------------------------------------------------------

class TestAcceptance:
    def test_canonical_two_bars_in_zone(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=2)
        bars = [
            mk_bar(open=9.5, high=10.5, low=9.5, close=10.2, volume=1000, offset_min=0),
            mk_bar(open=10.2, high=10.8, low=10.1, close=10.7, volume=1000, offset_min=1),
        ]
        result = a.check_confirmation(None, bars)
        assert result.confirmed

    def test_first_bar_outside_fails(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=2)
        bars = [
            mk_bar(open=9.5, high=9.9, low=9.4, close=9.8, volume=1000, offset_min=0),
            mk_bar(open=10.0, high=10.5, low=9.9, close=10.5, volume=1000, offset_min=1),
        ]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed
        assert "in zone" in result.reason

    def test_callable_bounds(self):
        # Bound derived from level metadata
        level = Level(
            price=10.5, kind="VAH", session_date=date(2026, 5, 17),
            metadata={"vah": 11.0, "val": 10.0},
        )
        a = Acceptance(
            zone_low=lambda lvl, bars: lvl.metadata["val"],
            zone_high=lambda lvl, bars: lvl.metadata["vah"],
            min_bars=2,
        )
        bars = [
            mk_bar(open=10.2, high=10.8, low=10.1, close=10.5, volume=1000, offset_min=0),
            mk_bar(open=10.5, high=10.9, low=10.4, close=10.8, volume=1000, offset_min=1),
        ]
        result = a.check_confirmation(level, bars)
        assert result.confirmed

    def test_min_bars_three(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=3)
        bars = [
            mk_bar(open=10.0, high=10.5, low=10.0, close=10.3, volume=1000, offset_min=0),
            mk_bar(open=10.3, high=10.8, low=10.3, close=10.5, volume=1000, offset_min=1),
            mk_bar(open=10.5, high=10.9, low=10.5, close=10.8, volume=1000, offset_min=2),
        ]
        result = a.check_confirmation(None, bars)
        assert result.confirmed

    def test_min_bars_three_only_two_in_zone(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=3)
        bars = [
            mk_bar(open=9.0, high=9.5, low=8.9, close=9.4, volume=1000, offset_min=0),
            mk_bar(open=10.3, high=10.8, low=10.3, close=10.5, volume=1000, offset_min=1),
            mk_bar(open=10.5, high=10.9, low=10.5, close=10.8, volume=1000, offset_min=2),
        ]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed

    def test_insufficient_bars(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=5)
        bars = [
            mk_bar(open=10.5, high=10.8, low=10.4, close=10.6, volume=1000, offset_min=0),
        ]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed
        assert "need 5 bars" in result.reason

    def test_empty_bars(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0)
        result = a.check_confirmation(None, [])
        assert not result.confirmed

    def test_invalid_zone(self):
        a = Acceptance(zone_low=11.0, zone_high=10.0)
        bars = [mk_bar(open=10.5, high=10.8, low=10.4, close=10.6, offset_min=i) for i in range(2)]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed
        assert "invalid zone" in result.reason

    def test_nan_close(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=2)
        bars = [
            mk_bar(open=10.5, high=10.8, low=10.4, close=10.6, offset_min=0),
            mk_bar(open=10.5, high=10.8, low=10.4, close=float("nan"), offset_min=1),
        ]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed
        assert "nan" in result.reason.lower()

    def test_close_exactly_on_boundary(self):
        """Close at boundary is considered inside (inclusive)."""
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=2)
        bars = [
            mk_bar(open=10.0, high=10.5, low=9.95, close=10.0, offset_min=0),
            mk_bar(open=10.5, high=11.05, low=10.4, close=11.0, offset_min=1),
        ]
        result = a.check_confirmation(None, bars)
        assert result.confirmed

    def test_min_bars_zero_rejects(self):
        a = Acceptance(zone_low=10.0, zone_high=11.0, min_bars=0)
        bars = [mk_bar(open=10.5, high=10.8, low=10.4, close=10.6, offset_min=0)]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed
        assert "min_bars" in result.reason

    def test_callable_raising_handled(self):
        def bad_low(level, bars):
            raise KeyError("missing_key")

        a = Acceptance(zone_low=bad_low, zone_high=11.0, min_bars=2)
        bars = [mk_bar(open=10.5, high=10.8, low=10.4, close=10.6, offset_min=i) for i in range(2)]
        result = a.check_confirmation(None, bars)
        assert not result.confirmed
        assert "zone resolver" in result.reason


# ---------------------------------------------------------------------------
# Rejection — >= 10 cases
# ---------------------------------------------------------------------------

class TestRejection:
    def test_resistance_rejection(self):
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDH")
        # Prior bar pokes above 10.0, entry closes below
        bars = [
            mk_bar(open=9.8, high=10.20, low=9.7, close=10.10, volume=2000, offset_min=0),
            mk_bar(open=10.10, high=10.15, low=9.7, close=9.85, volume=3000, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert result.confirmed
        assert result.pattern_name == "rejection_down"

    def test_support_rejection(self):
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDL")
        bars = [
            mk_bar(open=10.2, high=10.3, low=9.80, close=9.90, volume=2000, offset_min=0),
            mk_bar(open=9.90, high=10.30, low=9.85, close=10.15, volume=3000, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert result.confirmed
        assert result.pattern_name == "rejection_up"

    def test_no_test_of_level(self):
        """Price never poked the level -> no rejection."""
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDH")
        bars = [
            mk_bar(open=9.5, high=9.7, low=9.4, close=9.6, offset_min=0),
            mk_bar(open=9.6, high=9.8, low=9.5, close=9.7, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert not result.confirmed
        assert "no test" in result.reason

    def test_resistance_test_but_close_above_level(self):
        """Tested resistance but closed above -> NOT a rejection (it's a breakout)."""
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDH")
        bars = [
            mk_bar(open=9.8, high=10.20, low=9.7, close=10.10, offset_min=0),
            mk_bar(open=10.10, high=10.30, low=10.00, close=10.20, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert not result.confirmed
        assert "did not return" in result.reason

    def test_support_test_but_close_below_level(self):
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDL")
        bars = [
            mk_bar(open=10.2, high=10.3, low=9.80, close=9.90, offset_min=0),
            mk_bar(open=9.90, high=10.00, low=9.70, close=9.85, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert not result.confirmed

    def test_lookback_window(self):
        """The test bar can be within the lookback window, not just the entry bar."""
        r = Rejection(lookback_bars=3)
        level = mk_level(10.0, kind="PDH")
        bars = [
            mk_bar(open=9.7, high=10.20, low=9.7, close=10.10, offset_min=0),  # touch
            mk_bar(open=10.10, high=10.10, low=9.85, close=9.90, offset_min=1),  # retest
            mk_bar(open=9.90, high=9.99, low=9.80, close=9.85, offset_min=2),  # close below
        ]
        result = r.check_confirmation(level, bars)
        assert result.confirmed

    def test_no_level(self):
        r = Rejection()
        bars = [mk_bar(open=10.0, high=10.0, low=10.0, close=10.0, offset_min=0)]
        result = r.check_confirmation(None, bars)
        assert not result.confirmed

    def test_empty_bars(self):
        r = Rejection()
        result = r.check_confirmation(mk_level(10.0), [])
        assert not result.confirmed

    def test_nan_entry_ohlc_rejects(self):
        """NaN OHLC on entry bar rejects gracefully (no exception)."""
        r = Rejection()
        level = mk_level(10.0, kind="PDH")
        bars = [
            mk_bar(open=9.8, high=10.20, low=9.7, close=10.10, offset_min=0),
            mk_bar(open=10.10, high=float("nan"), low=9.7, close=9.85, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert not result.confirmed
        assert "nan" in result.reason.lower()

    def test_nan_prior_high_skipped(self):
        """NaN on a prior bar is filtered out; if entry alone tests the level, still confirms."""
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDH")
        bars = [
            mk_bar(open=9.8, high=float("nan"), low=9.7, close=10.10, offset_min=0),
            mk_bar(open=10.10, high=10.15, low=9.7, close=9.85, offset_min=1),
        ]
        # Entry bar alone qualifies as a test (high=10.15 > 10.0) and close
        # returned below — rejection is still confirmed despite prior NaN.
        result = r.check_confirmation(level, bars)
        assert result.confirmed
        assert result.pattern_name == "rejection_down"

    def test_explicit_side_override(self):
        """Force support side even though kind looks like resistance."""
        r = Rejection(lookback_bars=2, side="support")
        level = mk_level(10.0, kind="PDH")  # kind says resistance, but we override
        bars = [
            mk_bar(open=10.2, high=10.3, low=9.80, close=9.90, offset_min=0),
            mk_bar(open=9.90, high=10.30, low=9.85, close=10.15, offset_min=1),
        ]
        result = r.check_confirmation(level, bars)
        assert result.confirmed
        assert result.pattern_name == "rejection_up"

    def test_invalid_lookback(self):
        r = Rejection(lookback_bars=0)
        result = r.check_confirmation(
            mk_level(10.0), [mk_bar(open=10.0, high=10.0, low=10.0, close=10.0, offset_min=0)]
        )
        assert not result.confirmed
        assert "lookback_bars" in result.reason

    def test_strength_higher_for_deeper_poke(self):
        r = Rejection(lookback_bars=2)
        level = mk_level(10.0, kind="PDH")
        shallow = [
            mk_bar(open=9.9, high=10.05, low=9.85, close=9.98, offset_min=0),
            mk_bar(open=9.98, high=10.02, low=9.85, close=9.90, offset_min=1),
        ]
        deep = [
            mk_bar(open=9.9, high=10.50, low=9.85, close=10.20, offset_min=0),
            mk_bar(open=10.20, high=10.30, low=9.50, close=9.60, offset_min=1),
        ]
        s_shallow = r.check_confirmation(level, shallow)
        s_deep = r.check_confirmation(level, deep)
        assert s_shallow.confirmed and s_deep.confirmed
        assert s_deep.strength >= s_shallow.strength


# ---------------------------------------------------------------------------
# VolumeConfirm — >= 10 cases
# ---------------------------------------------------------------------------

class TestVolumeConfirm:
    def test_prior_bar_above_threshold(self):
        vc = VolumeConfirm(min_relative_volume=1.5, comparison="prior_bar")
        bars = [
            mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=2000, offset_min=1),
        ]
        result = vc.check_confirmation(None, bars)
        assert result.confirmed

    def test_prior_bar_below_threshold(self):
        vc = VolumeConfirm(min_relative_volume=2.0, comparison="prior_bar")
        bars = [
            mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=1500, offset_min=1),
        ]
        result = vc.check_confirmation(None, bars)
        assert not result.confirmed

    def test_twenty_bar_avg(self):
        vc = VolumeConfirm(min_relative_volume=2.0, comparison="20_bar_avg")
        hist = mk_series(n=20, base_vol=1000)
        entry = mk_bar(open=10, high=10, low=10, close=10, volume=2500, offset_min=21)
        result = vc.check_confirmation(None, hist + [entry])
        assert result.confirmed

    def test_session_avg(self):
        vc = VolumeConfirm(min_relative_volume=1.5, comparison="session_avg")
        hist = mk_series(n=10, base_vol=2000)
        entry = mk_bar(open=10, high=10, low=10, close=10, volume=4000, offset_min=11)
        result = vc.check_confirmation(None, hist + [entry])
        assert result.confirmed

    def test_no_bars(self):
        vc = VolumeConfirm()
        result = vc.check_confirmation(None, [])
        assert not result.confirmed

    def test_only_entry_bar_prior_comparison(self):
        vc = VolumeConfirm(min_relative_volume=1.5, comparison="prior_bar")
        entry = mk_bar(open=10, high=10, low=10, close=10, volume=5000, offset_min=0)
        result = vc.check_confirmation(None, [entry])
        assert not result.confirmed
        assert "missing" in result.reason

    def test_nan_entry_volume(self):
        vc = VolumeConfirm()
        bars = [
            mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=float("nan"), offset_min=1),
        ]
        result = vc.check_confirmation(None, bars)
        assert not result.confirmed
        assert "nan" in result.reason.lower()

    def test_zero_prior_baseline(self):
        vc = VolumeConfirm(min_relative_volume=1.5, comparison="prior_bar")
        bars = [
            mk_bar(open=10, high=10, low=10, close=10, volume=0, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=5000, offset_min=1),
        ]
        result = vc.check_confirmation(None, bars)
        assert not result.confirmed
        assert "zero baseline" in result.reason

    def test_partial_20_bar_window_used(self):
        """Only 5 prior bars available — still computes avg of those."""
        vc = VolumeConfirm(min_relative_volume=2.0, comparison="20_bar_avg")
        hist = mk_series(n=5, base_vol=1000)
        entry = mk_bar(open=10, high=10, low=10, close=10, volume=2500, offset_min=6)
        result = vc.check_confirmation(None, hist + [entry])
        assert result.confirmed
        assert "5_bar_avg" in result.reason

    def test_strength_increases_with_ratio(self):
        vc = VolumeConfirm(min_relative_volume=1.0, comparison="prior_bar")
        low = [
            mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=1100, offset_min=1),
        ]
        high = [
            mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=10000, offset_min=1),
        ]
        s_low = vc.check_confirmation(None, low).strength
        s_high = vc.check_confirmation(None, high).strength
        assert s_high > s_low

    def test_strength_in_unit_interval(self):
        vc = VolumeConfirm(min_relative_volume=1.0)
        bars = [
            mk_bar(open=10, high=10, low=10, close=10, volume=1000, offset_min=0),
            mk_bar(open=10, high=10, low=10, close=10, volume=100000, offset_min=1),
        ]
        result = vc.check_confirmation(None, bars)
        assert 0.0 <= result.strength <= 1.0


# ---------------------------------------------------------------------------
# L2Confirm — >= 10 cases
# ---------------------------------------------------------------------------

class TestL2Confirm:
    def _state(self, **kwargs) -> dict:
        defaults = {
            "imbalance": 0.6,
            "imbalance_trend": "rising",
            "bid_stacking": False,
            "bid_stack_levels": [],
            "large_bid": False,
            "large_ask": False,
            "spread_pct": 0.5,
            "ask_thinning": False,
            "signals": [],
        }
        defaults.update(kwargs)
        return defaults

    def test_long_confirmed(self):
        l2c = L2Confirm(min_imbalance=0.55, max_spread_pct=1.0)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], self._state(imbalance=0.65))
        assert result.confirmed

    def test_long_imbalance_below_threshold(self):
        l2c = L2Confirm(min_imbalance=0.55, max_spread_pct=1.0)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], self._state(imbalance=0.50))
        assert not result.confirmed
        assert "imbalance" in result.reason

    def test_short_confirmed(self):
        l2c = L2Confirm(min_imbalance=0.55, max_spread_pct=1.0)
        result = l2c.check_confirmation(mk_level(10.0, "PDL"), [], self._state(imbalance=0.40))
        assert result.confirmed

    def test_short_imbalance_too_high(self):
        l2c = L2Confirm(min_imbalance=0.55, max_spread_pct=1.0)
        result = l2c.check_confirmation(mk_level(10.0, "PDL"), [], self._state(imbalance=0.50))
        assert not result.confirmed

    def test_spread_veto(self):
        l2c = L2Confirm(min_imbalance=0.55, max_spread_pct=1.0)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], self._state(spread_pct=2.5))
        assert not result.confirmed
        assert "spread" in result.reason

    def test_require_bid_stacking_present(self):
        l2c = L2Confirm(min_imbalance=0.55, require_bid_stacking=True)
        state = self._state(imbalance=0.65, bid_stacking=True)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert result.confirmed

    def test_require_bid_stacking_absent(self):
        l2c = L2Confirm(min_imbalance=0.55, require_bid_stacking=True)
        state = self._state(imbalance=0.65, bid_stacking=False)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert not result.confirmed
        assert "bid_stacking" in result.reason

    def test_no_l2_state_strict(self):
        l2c = L2Confirm(pass_through_on_missing=False)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], None)
        assert not result.confirmed
        assert "no L2" in result.reason

    def test_no_l2_state_pass_through(self):
        l2c = L2Confirm(pass_through_on_missing=True)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], None)
        assert result.confirmed
        assert result.strength == 0.0

    def test_missing_imbalance_key(self):
        l2c = L2Confirm()
        state = self._state()
        state.pop("imbalance")
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert not result.confirmed
        assert "imbalance" in result.reason

    def test_nan_imbalance(self):
        l2c = L2Confirm()
        state = self._state(imbalance=float("nan"))
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert not result.confirmed

    def test_explicit_long_direction_with_no_level(self):
        l2c = L2Confirm(min_imbalance=0.55, direction="long")
        result = l2c.check_confirmation(None, [], self._state(imbalance=0.65))
        assert result.confirmed

    def test_short_with_ask_stacking_required_bid_stacking_present_with_ask_signal(self):
        """Short ask-stacking requirement: bid stacking present is OK if ask signals exist."""
        l2c = L2Confirm(min_imbalance=0.55, direction="short", require_ask_stacking=True)
        state = self._state(imbalance=0.40, bid_stacking=True, large_ask=True)
        result = l2c.check_confirmation(mk_level(10.0, "PDL"), [], state)
        # bid_stacking present + large_ask present -> the OR allows it
        assert result.confirmed

    def test_short_with_ask_stacking_required_bid_stacking_no_ask_signal(self):
        l2c = L2Confirm(min_imbalance=0.55, direction="short", require_ask_stacking=True)
        state = self._state(imbalance=0.40, bid_stacking=True, large_ask=False, ask_thinning=False)
        result = l2c.check_confirmation(mk_level(10.0, "PDL"), [], state)
        assert not result.confirmed

    def test_strength_in_unit_interval(self):
        l2c = L2Confirm(min_imbalance=0.55)
        state = self._state(imbalance=0.95, bid_stacking=True, large_bid=True)
        result = l2c.check_confirmation(mk_level(10.0, "PDH"), [], state)
        assert 0.0 <= result.strength <= 1.0


# ---------------------------------------------------------------------------
# Cross-cutting: ConfirmationResult invariants
# ---------------------------------------------------------------------------

class TestConfirmationResultInvariants:
    def test_strength_clamped_above_one(self):
        r = ConfirmationResult(confirmed=True, pattern_name="test", strength=1.5)
        assert r.strength == 1.0

    def test_strength_clamped_below_zero(self):
        r = ConfirmationResult(confirmed=False, pattern_name="test", strength=-0.5)
        assert r.strength == 0.0
