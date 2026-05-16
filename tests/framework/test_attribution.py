"""Unit tests for framework.attribution.StrategyAttribution."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytz

from framework.attribution import (
    StrategyAttribution,
    TRADING_DAYS_PER_YEAR,
    _trade_log_path,
)

ET = pytz.timezone("US/Eastern")


@pytest.fixture
def attrib(tmp_path: Path) -> StrategyAttribution:
    return StrategyAttribution(state_dir=tmp_path)


def _ts(hour: int, minute: int = 0) -> datetime:
    return ET.localize(datetime(2026, 5, 14, hour, minute, 0))


class TestStrategyAttributionRecording:
    def test_basic_long_pnl(self, attrib: StrategyAttribution, tmp_path: Path):
        rec = attrib.record_trade(
            strategy_name="ORB",
            symbol="VERO",
            entry_time=_ts(10, 0),
            exit_time=_ts(10, 15),
            entry_price=5.00,
            exit_price=5.50,
            qty=100,
            side="long",
            exit_reason="target_2R",
            risk_per_share=0.20,
        )
        assert rec is not None
        assert rec.pnl == pytest.approx(50.0)
        # R-multiple: 0.50 / 0.20 = 2.5
        assert rec.r_multiple == pytest.approx(2.5)
        assert rec.hold_seconds == pytest.approx(900.0)

        path = _trade_log_path("2026-05-14", tmp_path)
        assert path.exists()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["strategy_name"] == "ORB"
        assert d["pnl"] == pytest.approx(50.0)

    def test_short_pnl_sign(self, attrib: StrategyAttribution):
        rec = attrib.record_trade(
            strategy_name="PDH-fade",
            symbol="ATRA",
            entry_time=_ts(11, 0),
            exit_time=_ts(11, 10),
            entry_price=10.00,
            exit_price=9.50,
            qty=200,
            side="short",
            exit_reason="target",
            risk_per_share=0.30,
        )
        # Short, price down → win
        assert rec.pnl == pytest.approx(200 * (10.00 - 9.50))  # 100
        # R = (9.50 - 10.00) * -1 / 0.30 = 0.50 / 0.30
        assert rec.r_multiple == pytest.approx(0.50 / 0.30)

    def test_invalid_inputs_return_none(self, attrib: StrategyAttribution):
        assert attrib.record_trade("", "X", _ts(10), _ts(11), 5, 5, 100, "long", "x") is None
        assert attrib.record_trade("S", "", _ts(10), _ts(11), 5, 5, 100, "long", "x") is None
        assert attrib.record_trade("S", "X", _ts(10), _ts(11), 5, 5, 0, "long", "x") is None
        assert attrib.record_trade("S", "X", _ts(10), _ts(11), 5, 5, 100, "neither", "x") is None
        assert attrib.record_trade("S", "X", _ts(10), _ts(11), float("nan"), 5, 100, "long", "x") is None


class TestStrategyAttributionAggregation:
    """Five-trade mixed sequence across two strategies. Manual P&L:
        ORB: +50, -20, +30 → gross 60, wins 2/3
        VWAP: -40, +80     → gross 40, wins 1/2
    Portfolio: 100, wins 3/5.
    """

    def _setup_five_trades(self, attrib: StrategyAttribution):
        # ORB +50
        attrib.record_trade(
            "ORB", "AAA", _ts(10, 0), _ts(10, 10),
            5.00, 5.50, 100, "long", "target", risk_per_share=0.20,
        )
        # ORB -20
        attrib.record_trade(
            "ORB", "BBB", _ts(10, 30), _ts(10, 40),
            5.00, 4.80, 100, "long", "stop", risk_per_share=0.20,
        )
        # ORB +30
        attrib.record_trade(
            "ORB", "CCC", _ts(11, 0), _ts(11, 10),
            5.00, 5.30, 100, "long", "trail", risk_per_share=0.20,
        )
        # VWAP -40
        attrib.record_trade(
            "VWAP", "AAA", _ts(11, 30), _ts(11, 40),
            10.00, 9.60, 100, "long", "stop", risk_per_share=0.40,
        )
        # VWAP +80
        attrib.record_trade(
            "VWAP", "DDD", _ts(12, 0), _ts(12, 15),
            10.00, 10.80, 100, "long", "target", risk_per_share=0.40,
        )

    def test_aggregates_match_manual(self, attrib: StrategyAttribution):
        self._setup_five_trades(attrib)
        summary = attrib.strategy_attribution_summary("2026-05-14")
        orb = summary["ORB"]
        vwap = summary["VWAP"]
        port = summary["__portfolio__"]

        assert orb["trades"] == 3
        assert orb["wins"] == 2
        assert orb["gross_pnl"] == pytest.approx(60.0)
        assert orb["win_rate"] == pytest.approx(2 / 3)
        # avg R for ORB: (2.5, -1.0, 1.5)/3 = 1.0
        assert orb["avg_r"] == pytest.approx(1.0)
        # profit factor: wins=80, losses=20 → 4.0
        assert orb["profit_factor"] == pytest.approx(80.0 / 20.0)

        assert vwap["trades"] == 2
        assert vwap["wins"] == 1
        assert vwap["gross_pnl"] == pytest.approx(40.0)

        assert port["trades"] == 5
        assert port["wins"] == 3
        assert port["gross_pnl"] == pytest.approx(100.0)

    def test_sharpe_matches_reference(self, attrib: StrategyAttribution):
        """Sharpe = mean/std (sample) * sqrt(252)."""
        self._setup_five_trades(attrib)
        summary = attrib.strategy_attribution_summary("2026-05-14")
        orb_pnls = [50.0, -20.0, 30.0]
        mean = sum(orb_pnls) / 3
        var = sum((p - mean) ** 2 for p in orb_pnls) / 2  # n-1
        std = math.sqrt(var)
        expected = (mean / std) * math.sqrt(TRADING_DAYS_PER_YEAR)
        assert summary["ORB"]["sharpe"] == pytest.approx(expected)

    def test_max_drawdown_computation(self, attrib: StrategyAttribution):
        """Equity sequence: +100, -30, +20, -50, +60.
        Cumulative: 100, 70, 90, 40, 100. Peaks: 100, 100, 100, 100, 100.
        Drawdowns: 0, 30, 10, 60, 0. Max = 60.
        """
        seq = [100.0, -30.0, 20.0, -50.0, 60.0]
        for i, p in enumerate(seq):
            attrib.record_trade(
                "S", f"T{i}", _ts(10, i), _ts(10, i + 1),
                entry_price=10.0,
                exit_price=10.0 + p / 100.0,
                qty=100,
                side="long",
                exit_reason="test",
            )
        summary = attrib.strategy_attribution_summary("2026-05-14")
        assert summary["S"]["max_drawdown"] == pytest.approx(60.0)

    def test_zero_trades_safe(self, attrib: StrategyAttribution):
        summary = attrib.strategy_attribution_summary("2099-01-01")
        # No trades that day → only __portfolio__ row with zeros
        assert summary["__portfolio__"]["trades"] == 0
        assert summary["__portfolio__"]["sharpe"] == 0.0

    def test_profit_factor_no_losses(self, attrib: StrategyAttribution):
        """All-win sequence → profit_factor = inf (gross_losses=0)."""
        attrib.record_trade(
            "X", "A", _ts(10), _ts(10, 5), 5.0, 5.10, 100, "long", "ok",
        )
        summary = attrib.strategy_attribution_summary("2026-05-14")
        assert math.isinf(summary["X"]["profit_factor"])


class TestStrategyAttributionFilePaths:
    def test_file_per_entry_date(self, attrib: StrategyAttribution, tmp_path: Path):
        attrib.record_trade(
            "S", "A", _ts(10), _ts(11), 5, 5.10, 100, "long", "ok",
        )
        # Next day:
        next_day = ET.localize(datetime(2026, 5, 15, 10, 0))
        attrib.record_trade(
            "S", "B", next_day, next_day + timedelta(minutes=10),
            5, 5.10, 100, "long", "ok",
        )
        assert _trade_log_path("2026-05-14", tmp_path).exists()
        assert _trade_log_path("2026-05-15", tmp_path).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
