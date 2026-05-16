"""Tiered-sizer integration tests for backtest.portfolio_backtest.

Verifies:
  - SizingMode.tiered() instantiates a wired TieredSizer
  - SizingMode.size() routes through TieredSizer.size for tiered mode
  - tier_lock=True flag survives the round trip — no advancement applied
    even when equity grows past every tier floor

These tests do NOT spin up the full run_portfolio_backtest engine (which
needs a tick_cache_databento dataset).  They drive SizingMode.size +
TieredSizer.on_session_close directly, which is exactly the path the
engine exercises per bar / per session.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path("/Users/duffy/warrior_bot_v2")
sys.path.insert(0, str(REPO))

from backtest.portfolio_backtest import SizingMode
from framework.sizing import TieredSizer


def _passing_returns(n: int = 60) -> list[float]:
    out = []
    for i in range(n):
        out.append(0.005 + (0.0005 if i % 2 == 0 else -0.0005))
    return out


def _weekday_sessions(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class TestSizingModeTieredIntegration:
    def test_tiered_factory_binds_sizer(self, tmp_path: Path) -> None:
        sm = SizingMode.tiered(
            initial_tier=1, tier_lock=False, auto_advance=True,
            state_path=tmp_path / "tier.json",
        )
        assert sm.name == "tiered"
        assert isinstance(sm.tiered_sizer, TieredSizer)
        assert sm.tiered_sizer.current_tier == 1

    def test_size_returns_tier1_risk_dollars(self, tmp_path: Path) -> None:
        """Engine call: SizingMode.size(...) should yield $300 risk at tier 1."""
        sm = SizingMode.tiered(
            initial_tier=1, state_path=tmp_path / "tier.json",
        )
        qty, risk = sm.size(
            equity=25_000, entry_price=5.0, stop_price=4.5,
            recent_bar_volume=1_000_000,
        )
        # 300 / 0.5 = 600 shares, $300 risk
        assert qty == 600
        assert risk == pytest.approx(300.0)

    def test_size_at_tier7_yields_2500_risk(self, tmp_path: Path) -> None:
        sm = SizingMode.tiered(
            initial_tier=7, state_path=tmp_path / "tier.json",
        )
        qty, risk = sm.size(
            equity=250_000, entry_price=10.0, stop_price=9.0,
            recent_bar_volume=10_000_000,
        )
        assert risk == pytest.approx(2500.0)
        assert qty == 2500  # 2500/1.0

    def test_tier_lock_survives_through_sizing_mode(self, tmp_path: Path) -> None:
        """The Wave 4 paper guarantee: tier_lock=True keeps risk at $300.

        Drive equity through tier 7 levels via on_session_close calls;
        SizingMode.size at the end must still return $300 risk.
        """
        sm = SizingMode.tiered(
            initial_tier=1, tier_lock=True, auto_advance=True,
            state_path=tmp_path / "tier.json",
        )
        sessions = _weekday_sessions(date(2026, 6, 1), 80)
        returns = _passing_returns(80)

        # Grow equity from $25K to $300K over 80 sessions
        equity = 25_000.0
        for i, d in enumerate(sessions):
            equity = 25_000 + i * 4_000  # past $250K by session ~57
            sm.tiered_sizer.on_session_close(
                session_date=d, equity=equity, portfolio_returns=returns,
            )

        # Tier stays at 1 — verify both directly and via SizingMode.size
        assert sm.tiered_sizer.current_tier == 1
        qty, risk = sm.size(
            equity=equity, entry_price=10.0, stop_price=9.0,
            recent_bar_volume=10_000_000,
        )
        assert risk == pytest.approx(300.0)
        assert qty == 300  # $300 / $1 R = 300 shares

    def test_auto_advance_false_through_sizing_mode(self, tmp_path: Path) -> None:
        """auto_advance=False: transitions staged not applied."""
        sm = SizingMode.tiered(
            initial_tier=1, tier_lock=False, auto_advance=False,
            state_path=tmp_path / "tier.json",
        )
        sessions = _weekday_sessions(date(2026, 6, 1), 30)
        returns = _passing_returns(60)

        for i, d in enumerate(sessions[:20]):
            sm.tiered_sizer.on_session_close(
                session_date=d, equity=30_000 + i * 200, portfolio_returns=returns,
            )
        for d in sessions[20:23]:
            sm.tiered_sizer.on_session_close(
                session_date=d, equity=42_000, portfolio_returns=returns,
            )

        # Tier 1 with pending transition staged
        assert sm.tiered_sizer.current_tier == 1
        assert sm.tiered_sizer.pending_transition is not None
        assert sm.tiered_sizer.pending_transition["to"] == 2

        # SizingMode.size still returns $300 risk
        qty, risk = sm.size(42_000, 5.0, 4.5, 1_000_000)
        assert risk == pytest.approx(300.0)


class TestSizingModeBackwardCompat:
    """Ensure the new tier mode doesn't break fixed_dollar / half_kelly."""

    def test_fixed_dollar_unchanged(self) -> None:
        sm = SizingMode(name="fixed_dollar", fixed_dollar_risk=1000.0)
        qty, risk = sm.size(50_000, 5.0, 4.0, 10_000_000)
        assert risk == 1000.0
        assert qty == 1000

    def test_half_kelly_unchanged(self) -> None:
        sm = SizingMode(name="half_kelly", risk_per_trade_pct=1.0)
        qty, risk = sm.size(30_000, 5.0, 4.75, 10_000_000)
        # half-Kelly 30000 * 1% / 2 = $150 risk
        assert risk == pytest.approx(150.0)
        # qty: 150 / 0.25 = 600
        assert qty == 600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
