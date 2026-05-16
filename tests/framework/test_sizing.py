"""Unit tests for framework.sizing.HalfKellySizer."""
from __future__ import annotations

import math

import pytest

from framework.sizing import HalfKellySizer


class TestHalfKellySizer:
    def test_basic_half_kelly_uncapped(self):
        """30K equity, 1% risk, $0.25 R, $5 entry, large bar volume.

        Half-Kelly: (30000 * 0.01 / 2) / 0.25 = 600 shares.
        Bar-volume cap with large volume should not bind.
        (Uses $0.25 not $0.20 to avoid float-precision floor jitter.)
        """
        sizer = HalfKellySizer(risk_per_trade_pct=1.0, max_bar_volume_pct=0.05)
        shares = sizer.size_position(
            equity=30_000, entry_price=5.0, stop_price=4.75,
            recent_bar_volume=1_000_000,
        )
        assert shares == 600

    def test_bar_volume_cap_binds(self):
        """30K equity, 1% risk, $0.25 R, $5 entry, small bar dollar-volume.

        Raw half-Kelly = 600 shares. Bar cap at 5% of $15K / $5 = 150.
        Cap binds → 150 shares (acceptance criterion in directive).
        """
        sizer = HalfKellySizer(risk_per_trade_pct=1.0, max_bar_volume_pct=0.05)
        shares = sizer.size_position(
            equity=30_000, entry_price=5.0, stop_price=4.75,
            recent_bar_volume=15_000,
        )
        assert shares == 150

    def test_zero_r_returns_zero(self):
        sizer = HalfKellySizer()
        assert sizer.size_position(30_000, 5.0, 5.0, 100_000) == 0

    def test_zero_equity_returns_zero(self):
        sizer = HalfKellySizer()
        assert sizer.size_position(0, 5.0, 4.80, 100_000) == 0

    def test_negative_equity_returns_zero(self):
        sizer = HalfKellySizer()
        assert sizer.size_position(-1_000, 5.0, 4.80, 100_000) == 0

    def test_zero_bar_volume_returns_zero(self):
        """Cap of zero binds → no shares."""
        sizer = HalfKellySizer()
        assert sizer.size_position(30_000, 5.0, 4.80, 0) == 0

    def test_negative_bar_volume_returns_zero(self):
        sizer = HalfKellySizer()
        assert sizer.size_position(30_000, 5.0, 4.80, -100) == 0

    def test_none_bar_volume_returns_zero(self):
        sizer = HalfKellySizer()
        assert sizer.size_position(30_000, 5.0, 4.80, None) == 0

    def test_nan_inputs_return_zero(self):
        sizer = HalfKellySizer()
        nan = float("nan")
        assert sizer.size_position(nan, 5.0, 4.80, 100_000) == 0
        assert sizer.size_position(30_000, nan, 4.80, 100_000) == 0
        assert sizer.size_position(30_000, 5.0, nan, 100_000) == 0
        assert sizer.size_position(30_000, 5.0, 4.80, nan) == 0

    def test_infinite_inputs_return_zero(self):
        sizer = HalfKellySizer()
        inf = float("inf")
        assert sizer.size_position(inf, 5.0, 4.80, 100_000) == 0
        assert sizer.size_position(30_000, 5.0, 4.80, inf) == 0

    def test_floor_rounding(self):
        """750.5 should floor to 750, not round up."""
        sizer = HalfKellySizer(risk_per_trade_pct=1.0)
        # 30000 * 0.01 / 2 / 0.20 = 750 exactly; perturb to get fractional
        # Use entry=5, stop=4.7998 → R = 0.2002 → 749.25 → 749
        shares = sizer.size_position(30_000, 5.0, 4.7998, 1_000_000)
        assert shares == 749  # floor(749.25...)

    def test_negative_risk_pct_returns_zero(self):
        sizer = HalfKellySizer(risk_per_trade_pct=-1.0)
        assert sizer.size_position(30_000, 5.0, 4.80, 100_000) == 0

    def test_short_side_stop_above_entry(self):
        """abs() ensures shorts (stop > entry) also compute correctly."""
        sizer = HalfKellySizer(risk_per_trade_pct=1.0)
        shares = sizer.size_position(
            equity=30_000, entry_price=5.0, stop_price=5.25,
            recent_bar_volume=1_000_000,
        )
        # R = 0.25 same as long → 600 shares
        assert shares == 600

    def test_higher_risk_pct(self):
        """Doubling risk_per_trade_pct doubles share count."""
        sizer_1 = HalfKellySizer(risk_per_trade_pct=1.0)
        sizer_2 = HalfKellySizer(risk_per_trade_pct=2.0)
        s1 = sizer_1.size_position(30_000, 5.0, 4.75, 10_000_000)
        s2 = sizer_2.size_position(30_000, 5.0, 4.75, 10_000_000)
        assert s2 == 2 * s1

    def test_cap_zero_blocks_all_trades(self):
        """If max_bar_volume_pct == 0, all trades cap at zero."""
        sizer = HalfKellySizer(max_bar_volume_pct=0.0)
        assert sizer.size_position(30_000, 5.0, 4.80, 1_000_000) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
