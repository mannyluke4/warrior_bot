"""Unit tests for framework.risk.RiskManager."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from framework.risk import RiskManager, RiskConfig


@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    return tmp_path / "risk_state.json"


class TestRiskManagerKillSwitches:
    def test_per_strategy_daily_loss_triggers(self, tmp_state: Path):
        rm = RiskManager(
            per_strategy_daily_loss_pct=3.0, state_path=tmp_state
        )
        # Take a $300 loss on $10K equity = 3% — should kill
        rm.record_trade("ORB", pnl=-300.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("ORB", current_equity=10_000) is True

    def test_per_strategy_daily_loss_just_below_threshold(self, tmp_state: Path):
        rm = RiskManager(
            per_strategy_daily_loss_pct=3.0, state_path=tmp_state
        )
        rm.record_trade("ORB", pnl=-299.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("ORB", current_equity=10_000) is False

    def test_drawdown_triggers(self, tmp_state: Path):
        """+$1000 then -$600. Peak = $11000, current = $10400.
        DD = 600/11000 = 5.45% → kill at 5% threshold."""
        rm = RiskManager(
            per_strategy_drawdown_pct=5.0,
            per_strategy_daily_loss_pct=99.0,  # disable daily-loss
            consecutive_losses_kill=99,
            state_path=tmp_state,
        )
        rm.record_trade("VWAP", pnl=1000.0, equity_at_entry=10_000)
        rm.record_trade("VWAP", pnl=-600.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("VWAP", current_equity=10_000) is True

    def test_consecutive_losses_triggers(self, tmp_state: Path):
        rm = RiskManager(
            consecutive_losses_kill=3,
            per_strategy_daily_loss_pct=99.0,
            per_strategy_drawdown_pct=99.0,
            state_path=tmp_state,
        )
        for _ in range(3):
            rm.record_trade("PDH", pnl=-50.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("PDH", current_equity=10_000) is True

    def test_consecutive_losses_reset_on_win(self, tmp_state: Path):
        rm = RiskManager(
            consecutive_losses_kill=3,
            per_strategy_daily_loss_pct=99.0,
            per_strategy_drawdown_pct=99.0,
            state_path=tmp_state,
        )
        rm.record_trade("PDH", pnl=-50.0, equity_at_entry=10_000)
        rm.record_trade("PDH", pnl=-50.0, equity_at_entry=10_000)
        rm.record_trade("PDH", pnl=10.0, equity_at_entry=10_000)  # reset
        rm.record_trade("PDH", pnl=-50.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("PDH", current_equity=10_000) is False

    def test_portfolio_kill(self, tmp_state: Path):
        rm = RiskManager(
            portfolio_daily_loss_pct=5.0,
            per_strategy_daily_loss_pct=99.0,
            state_path=tmp_state,
        )
        # Strategy A loses $300, B loses $300 → total $600 = 6% of $10K
        rm.record_trade("A", pnl=-300.0, equity_at_entry=10_000)
        rm.record_trade("B", pnl=-300.0, equity_at_entry=10_000)
        assert rm.check_portfolio_kill(current_equity=10_000) is True

    def test_portfolio_kill_not_triggered_below_threshold(self, tmp_state: Path):
        rm = RiskManager(
            portfolio_daily_loss_pct=5.0, state_path=tmp_state
        )
        rm.record_trade("A", pnl=-100.0, equity_at_entry=10_000)
        assert rm.check_portfolio_kill(current_equity=10_000) is False

    def test_unknown_strategy_returns_false(self, tmp_state: Path):
        rm = RiskManager(state_path=tmp_state)
        assert rm.check_strategy_kill("missing", 10_000) is False

    def test_invalid_equity_returns_false(self, tmp_state: Path):
        rm = RiskManager(state_path=tmp_state)
        rm.record_trade("X", pnl=-500, equity_at_entry=10_000)
        assert rm.check_strategy_kill("X", current_equity=0) is False
        assert rm.check_strategy_kill("X", current_equity=-100) is False

    def test_kill_persists_through_check(self, tmp_state: Path):
        """Once killed, stays killed for the rest of the session."""
        rm = RiskManager(
            per_strategy_daily_loss_pct=3.0, state_path=tmp_state
        )
        rm.record_trade("ORB", pnl=-400.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("ORB", 10_000) is True
        # Even with no further activity:
        assert rm.check_strategy_kill("ORB", 10_000) is True


class TestRiskManagerDailyReset:
    def test_reset_daily_clears_counters(self, tmp_state: Path):
        rm = RiskManager(
            per_strategy_daily_loss_pct=3.0,
            consecutive_losses_kill=3,
            state_path=tmp_state,
        )
        for _ in range(3):
            rm.record_trade("ORB", pnl=-200.0, equity_at_entry=10_000)
        assert rm.check_strategy_kill("ORB", 10_000) is True
        rm.reset_daily()
        # After reset, no kill
        assert rm.check_strategy_kill("ORB", 10_000) is False
        st = rm.get_strategy_state("ORB")
        assert st.daily_pnl == 0.0
        assert st.consecutive_losses == 0
        assert st.killed is False


class TestRiskManagerPersistence:
    def test_state_survives_reload(self, tmp_state: Path):
        rm = RiskManager(
            per_strategy_daily_loss_pct=3.0, state_path=tmp_state
        )
        rm.record_trade("ORB", pnl=-100.0, equity_at_entry=10_000)
        rm.record_trade("ORB", pnl=-50.0, equity_at_entry=10_000)
        # Reload
        rm2 = RiskManager(
            per_strategy_daily_loss_pct=3.0, state_path=tmp_state
        )
        st = rm2.get_strategy_state("ORB")
        assert st is not None
        assert st.daily_pnl == pytest.approx(-150.0)
        assert st.consecutive_losses == 2
        assert st.trade_count == 2

    def test_corrupt_file_starts_fresh(self, tmp_state: Path):
        tmp_state.parent.mkdir(parents=True, exist_ok=True)
        tmp_state.write_text("not valid json {{{")
        # Should not raise
        rm = RiskManager(state_path=tmp_state)
        assert rm.get_strategy_state("anything") is None

    def test_persist_uses_per_pid_tmp(self, tmp_state: Path):
        """The tmp file naming pattern should be <stem>.<pid>.tmp."""
        rm = RiskManager(state_path=tmp_state)
        rm.record_trade("X", pnl=10.0, equity_at_entry=10_000)
        # After atomic rename, the tmp should be gone; only the real file
        assert tmp_state.exists()
        # And no leftover stale tmps:
        leftovers = list(
            tmp_state.parent.glob(f"{tmp_state.stem}.*.tmp")
        )
        assert leftovers == []


class TestRiskManagerInvalidInputs:
    def test_nan_pnl_ignored(self, tmp_state: Path):
        rm = RiskManager(state_path=tmp_state)
        rm.record_trade("X", pnl=float("nan"), equity_at_entry=10_000)
        assert rm.get_strategy_state("X") is None

    def test_empty_strategy_name_ignored(self, tmp_state: Path):
        rm = RiskManager(state_path=tmp_state)
        rm.record_trade("", pnl=-100.0, equity_at_entry=10_000)
        assert rm.debug_state()["strategies"] == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
