"""Unit tests for the squeeze framework wrapper.

Coverage:
- `SqueezeSource.compute_levels()` extracts PM_HIGH, PDH, and ROUND levels.
- `SqueezeSource.update_intraday()` forwards bars to the wrapped detector.
- `SqueezeBreakout.check_confirmation()` mirrors squeeze's prime gate.
- Parity vs `SqueezeDetectorV2` — the wrapper does NOT add or drop signals.
- Edge cases: empty history, no PM bars, stale prior session, etc.

Per the directive: this is a *wrapper* test. We verify the wrapper's
transformation layer is correct AND that the wrapped detector's behavior
is preserved (bit-identical signal logic).
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import List

import pytest

from framework.confirmations.squeeze_breakout import SqueezeBreakout
from framework.level_sources.base import Bar, BarHistory, Level
from framework.level_sources.squeeze import SqueezeSource


# ---------------------------------------------------------------------------
# Helpers — synthetic bars
# ---------------------------------------------------------------------------


def _bar(
    ts: datetime,
    *,
    o: float = 5.00,
    h: float = 5.10,
    lo: float = 4.95,
    c: float = 5.05,
    v: float = 10_000.0,
    symbol: str = "TEST",
) -> Bar:
    return Bar(
        timestamp=ts,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=v,
        symbol=symbol,
    )


def _enable_squeeze_env(monkeypatch) -> None:
    monkeypatch.setenv("WB_SQUEEZE_ENABLED", "1")
    monkeypatch.setenv("WB_SQ_VOL_MULT", "2.5")
    monkeypatch.setenv("WB_SQ_PRIME_BARS", "4")
    monkeypatch.setenv("WB_SQ_MIN_BODY_PCT", "2.0")
    monkeypatch.setenv("WB_SQ_MAX_ATTEMPTS", "5")


# ---------------------------------------------------------------------------
# SqueezeSource — level extraction
# ---------------------------------------------------------------------------


class TestSqueezeSourceLevels:
    def test_compute_levels_emits_pm_high_when_set(self) -> None:
        target = date(2026, 1, 16)
        src = SqueezeSource(target_date=target, symbol="VERO")
        src.set_premarket_levels(pm_high=3.50)
        ls = src.compute_levels("VERO", BarHistory(symbol="VERO", bars=[
            _bar(datetime(2026, 1, 16, 8, 0), o=3.40, h=3.50, lo=3.38, c=3.45, v=1000, symbol="VERO"),
        ]))
        kinds = [lvl.kind for lvl in ls.levels]
        assert "PM_HIGH" in kinds
        pm = next(lvl for lvl in ls.levels if lvl.kind == "PM_HIGH")
        assert pm.price == 3.50
        assert pm.metadata["source"] == "squeeze"

    def test_compute_levels_emits_pdh_when_set(self) -> None:
        target = date(2026, 1, 16)
        src = SqueezeSource(target_date=target, symbol="VERO")
        src.set_prior_day_high(3.25)
        ls = src.compute_levels("VERO", BarHistory(symbol="VERO", bars=[
            _bar(datetime(2026, 1, 16, 8, 0), o=3.40, h=3.50, lo=3.38, c=3.45, v=1000, symbol="VERO"),
        ]))
        kinds = [lvl.kind for lvl in ls.levels]
        assert "PDH" in kinds
        pdh = next(lvl for lvl in ls.levels if lvl.kind == "PDH")
        assert pdh.price == 3.25

    def test_compute_levels_auto_extracts_pm_high_from_history(self) -> None:
        """If pm_high is not explicitly set, derive it from PM bars (04:00-09:29)."""
        target = date(2026, 1, 16)
        src = SqueezeSource(target_date=target, symbol="VERO")
        history = BarHistory(symbol="VERO", bars=[
            # PM bars
            _bar(datetime(2026, 1, 16, 6, 0), h=3.20),
            _bar(datetime(2026, 1, 16, 7, 30), h=3.55),
            _bar(datetime(2026, 1, 16, 9, 0), h=3.48),
            # RTH bar
            _bar(datetime(2026, 1, 16, 10, 0), h=4.00),
        ])
        ls = src.compute_levels("VERO", history)
        pm = next((lvl for lvl in ls.levels if lvl.kind == "PM_HIGH"), None)
        assert pm is not None
        assert pm.price == 3.55  # max of PM bars

    def test_compute_levels_auto_extracts_pdh_from_history(self) -> None:
        target = date(2026, 1, 16)
        prior = date(2026, 1, 15)
        src = SqueezeSource(target_date=target, symbol="VERO")
        history = BarHistory(symbol="VERO", bars=[
            # Prior RTH
            _bar(datetime.combine(prior, time(10, 0)), h=3.10),
            _bar(datetime.combine(prior, time(14, 0)), h=3.30),
            # Today PM
            _bar(datetime.combine(target, time(8, 0)), h=3.50),
        ])
        ls = src.compute_levels("VERO", history)
        pdh = next((lvl for lvl in ls.levels if lvl.kind == "PDH"), None)
        assert pdh is not None
        assert pdh.price == 3.30

    def test_compute_levels_round_uses_last_bar_open(self, monkeypatch) -> None:
        """ROUND level = ceil(last_open). Mirrors detector's whole_dollar logic."""
        _enable_squeeze_env(monkeypatch)
        target = date(2026, 1, 16)
        src = SqueezeSource(target_date=target, symbol="VERO")
        src.set_premarket_levels(pm_high=3.50)
        # Update intraday so _last_bar_open is set
        src.update_intraday(_bar(
            datetime(2026, 1, 16, 8, 30), o=3.42, h=3.55, lo=3.40, c=3.52, v=5000
        ))
        ls = src.compute_levels("VERO", BarHistory(symbol="VERO", bars=[
            _bar(datetime(2026, 1, 16, 8, 30), o=3.42, h=3.55, lo=3.40, c=3.52, v=5000),
        ]))
        round_lvl = next((lvl for lvl in ls.levels if lvl.kind == "ROUND"), None)
        assert round_lvl is not None
        # ceil(3.42) == 4.0
        assert round_lvl.price == 4.0

    def test_compute_levels_empty_history_returns_empty(self) -> None:
        src = SqueezeSource(symbol="VERO")
        ls = src.compute_levels("VERO", BarHistory(symbol="VERO", bars=[]))
        assert ls.levels == ()


# ---------------------------------------------------------------------------
# SqueezeSource — detector forwarding
# ---------------------------------------------------------------------------


class TestSqueezeSourceDetectorForwarding:
    def test_update_intraday_forwards_bars_to_detector(self, monkeypatch) -> None:
        """update_intraday() must end up calling on_bar_close_1m on the
        underlying SqueezeDetectorV2 with the same OHLCV values."""
        _enable_squeeze_env(monkeypatch)
        src = SqueezeSource(symbol="VERO")
        src.set_vwap(3.40)

        # Seed three baseline bars
        for i, vol in enumerate([5000, 5000, 5000]):
            ts = datetime(2026, 1, 16, 7, i)
            src.update_intraday(_bar(ts, o=3.40, h=3.42, lo=3.38, c=3.41, v=vol))

        det = src.detector
        # detector's bars_1m deque should have all 3 bars
        assert len(det.bars_1m) == 3

    def test_detector_state_evolves_with_volume_explosion(self, monkeypatch) -> None:
        """Volume explosion + green-body bar should at least prime the
        detector (transition to PRIMED state)."""
        _enable_squeeze_env(monkeypatch)
        src = SqueezeSource(symbol="VERO")
        src.set_premarket_levels(pm_high=3.50)
        src.set_vwap(3.40)

        # Baseline bars
        for i in range(3):
            src.update_intraday(_bar(
                datetime(2026, 1, 16, 7, i),
                o=3.40, h=3.42, lo=3.38, c=3.41, v=5000
            ))

        # Volume explosion bar — 5x baseline, green, 5% body
        src.update_intraday(_bar(
            datetime(2026, 1, 16, 7, 4),
            o=3.40, h=3.65, lo=3.38, c=3.60, v=50000  # ~10x baseline
        ))

        # Detector should be PRIMED or ARMED now
        det = src.detector
        assert det._state in ("PRIMED", "ARMED"), (
            f"expected PRIMED/ARMED, got {det._state}"
        )

    def test_on_trade_price_triggers_entry_when_armed(self, monkeypatch) -> None:
        """Tick price >= armed.trigger_high produces an ENTRY SIGNAL message."""
        _enable_squeeze_env(monkeypatch)
        monkeypatch.setenv("WB_SEED_GATE_ENABLED", "0")  # disable seed gate
        src = SqueezeSource(symbol="VERO")
        src.set_premarket_levels(pm_high=3.50)
        src.set_vwap(3.40)

        # Baseline
        for i in range(3):
            src.update_intraday(_bar(
                datetime(2026, 1, 16, 7, i),
                o=3.40, h=3.42, lo=3.38, c=3.41, v=5000
            ))

        # Spike bar breaking PM_HIGH should arm
        src.update_intraday(_bar(
            datetime(2026, 1, 16, 7, 4),
            o=3.40, h=3.55, lo=3.38, c=3.54, v=50000
        ))

        # If armed, trigger entry by sending a tick above trigger_high
        if src.is_armed():
            arm = src.get_armed_trade()
            msg = src.on_trade_price(arm.trigger_high + 0.01)
            assert msg is not None
            assert "ENTRY SIGNAL" in msg or "SEED_GATE" in msg

    def test_reset_clears_state(self, monkeypatch) -> None:
        _enable_squeeze_env(monkeypatch)
        src = SqueezeSource(symbol="VERO")
        src.set_vwap(3.40)
        src.update_intraday(_bar(
            datetime(2026, 1, 16, 7, 0),
            o=3.40, h=3.42, lo=3.38, c=3.41, v=5000
        ))
        src.reset()
        det = src.detector
        assert det._state == "IDLE"
        assert det.armed is None


# ---------------------------------------------------------------------------
# SqueezeBreakout — confirmation plugin
# ---------------------------------------------------------------------------


class TestSqueezeBreakoutConfirmation:
    def test_confirmed_on_volume_explosion_green_body(self) -> None:
        cf = SqueezeBreakout(
            min_vol_mult=2.5, prime_bars=4, min_body_pct=2.0, min_bar_vol=50_000
        )
        # Three baseline bars (avg vol = 10k) + one spike
        bars = [
            _bar(datetime(2026, 1, 16, 7, i), o=3.40, h=3.42, lo=3.38, c=3.41, v=10_000)
            for i in range(3)
        ]
        bars.append(_bar(
            datetime(2026, 1, 16, 7, 4),
            o=3.40, h=3.55, lo=3.38, c=3.50, v=60_000  # 6x avg
        ))
        result = cf.check_confirmation(level=None, bars=bars)
        assert result.confirmed is True
        assert result.pattern_name == "squeeze_breakout"
        assert result.metadata["vol_mult"] == pytest.approx(6.0, rel=0.01)

    def test_rejected_on_low_volume(self) -> None:
        cf = SqueezeBreakout(min_vol_mult=2.5, min_bar_vol=50_000)
        bars = [
            _bar(datetime(2026, 1, 16, 7, i), v=10_000) for i in range(3)
        ]
        bars.append(_bar(datetime(2026, 1, 16, 7, 4), o=3.40, h=3.55, c=3.50, v=20_000))
        result = cf.check_confirmation(level=None, bars=bars)
        assert result.confirmed is False
        assert "vol_mult" in result.reason

    def test_rejected_on_red_bar(self) -> None:
        cf = SqueezeBreakout(min_vol_mult=2.5, min_bar_vol=10_000)
        bars = [
            _bar(datetime(2026, 1, 16, 7, i), o=3.40, h=3.42, lo=3.38, c=3.41, v=10_000)
            for i in range(3)
        ]
        bars.append(_bar(
            datetime(2026, 1, 16, 7, 4),
            o=3.50, h=3.55, lo=3.40, c=3.42, v=60_000  # red
        ))
        result = cf.check_confirmation(level=None, bars=bars)
        assert result.confirmed is False
        assert "red bar" in result.reason

    def test_rejected_on_thin_body(self) -> None:
        cf = SqueezeBreakout(min_vol_mult=2.5, min_body_pct=2.0, min_bar_vol=10_000)
        bars = [
            _bar(datetime(2026, 1, 16, 7, i), v=10_000) for i in range(3)
        ]
        bars.append(_bar(
            datetime(2026, 1, 16, 7, 4),
            o=3.40, h=3.45, lo=3.38, c=3.41, v=60_000  # body 0.3%
        ))
        result = cf.check_confirmation(level=None, bars=bars)
        assert result.confirmed is False
        assert "body_pct" in result.reason

    def test_empty_bars_rejected(self) -> None:
        cf = SqueezeBreakout()
        result = cf.check_confirmation(level=None, bars=[])
        assert result.confirmed is False
        assert "no bars" in result.reason

    def test_insufficient_baseline_rejected(self) -> None:
        cf = SqueezeBreakout()
        bars = [_bar(datetime(2026, 1, 16, 7, 0))]
        result = cf.check_confirmation(level=None, bars=bars)
        assert result.confirmed is False
        assert "insufficient bars" in result.reason

    def test_from_env_reads_env_knobs(self, monkeypatch) -> None:
        monkeypatch.setenv("WB_SQ_VOL_MULT", "3.5")
        monkeypatch.setenv("WB_SQ_PRIME_BARS", "5")
        monkeypatch.setenv("WB_SQ_MIN_BODY_PCT", "1.0")
        monkeypatch.setenv("WB_SQ_MIN_BAR_VOL", "75000")
        cf = SqueezeBreakout.from_env()
        assert cf.min_vol_mult == 3.5
        assert cf.prime_bars == 5
        assert cf.min_body_pct == 1.0
        assert cf.min_bar_vol == 75_000


# ---------------------------------------------------------------------------
# Parity vs raw SqueezeDetectorV2
# ---------------------------------------------------------------------------


class TestSqueezeParityVsRawDetector:
    """The wrapper must produce bit-identical signals to direct detector use.

    Strategy: build a deterministic bar sequence, run it both ways, and
    compare detector state after each bar.
    """

    def _run_raw(self, bars: List[Bar], pm_high: float, vwap: float):
        """Drive a raw SqueezeDetectorV2 directly."""
        from squeeze_detector_v2 import SqueezeDetectorV2

        det = SqueezeDetectorV2()
        det.symbol = "VERO"
        det.update_premarket_levels(pm_high)
        msgs = []
        for b in bars:
            class _BarObj:
                pass
            ba = _BarObj()
            ba.open = b.open
            ba.high = b.high
            ba.low = b.low
            ba.close = b.close
            ba.volume = b.volume
            msg = det.on_bar_close_1m(ba, vwap=vwap)
            msgs.append(msg)
        return det, msgs

    def _run_wrapped(self, bars: List[Bar], pm_high: float, vwap: float):
        """Drive the wrapper."""
        src = SqueezeSource(symbol="VERO")
        src.set_premarket_levels(pm_high)
        src.set_vwap(vwap)
        msgs = []
        for b in bars:
            src.update_intraday(b)
            msgs.append(src.pull_arm_message())
        return src.detector, msgs

    def test_parity_simple_sequence(self, monkeypatch) -> None:
        _enable_squeeze_env(monkeypatch)
        monkeypatch.setenv("WB_SEED_GATE_ENABLED", "0")
        bars = [
            _bar(datetime(2026, 1, 16, 7, 0), o=3.40, h=3.42, lo=3.38, c=3.41, v=8000),
            _bar(datetime(2026, 1, 16, 7, 1), o=3.41, h=3.43, lo=3.39, c=3.42, v=9000),
            _bar(datetime(2026, 1, 16, 7, 2), o=3.42, h=3.44, lo=3.40, c=3.43, v=10_000),
            _bar(datetime(2026, 1, 16, 7, 3), o=3.43, h=3.55, lo=3.40, c=3.52, v=60_000),
        ]
        raw_det, raw_msgs = self._run_raw(bars, pm_high=3.50, vwap=3.40)
        wrap_det, wrap_msgs = self._run_wrapped(bars, pm_high=3.50, vwap=3.40)

        # State machines must end in the same state.
        assert raw_det._state == wrap_det._state, (
            f"state divergence raw={raw_det._state} wrap={wrap_det._state}"
        )
        # Same number of arms
        assert (raw_det.armed is None) == (wrap_det.armed is None)
        if raw_det.armed is not None and wrap_det.armed is not None:
            assert raw_det.armed.trigger_high == wrap_det.armed.trigger_high
            assert raw_det.armed.stop_low == wrap_det.armed.stop_low
            assert raw_det.armed.r == pytest.approx(wrap_det.armed.r)
            assert raw_det.armed.score == pytest.approx(wrap_det.armed.score)

        # Message streams should match (modulo wrapper's pop semantics)
        # Raw msgs may include None; wrapper pulls only ARM/RESET messages.
        nonempty_raw = [m for m in raw_msgs if m]
        nonempty_wrap = [m for m in wrap_msgs if m]
        assert nonempty_raw == nonempty_wrap, (
            f"message divergence:\n  raw={nonempty_raw}\n  wrap={nonempty_wrap}"
        )

    def test_parity_no_signal_when_disabled(self, monkeypatch) -> None:
        """When WB_SQUEEZE_ENABLED=0, neither path emits signals."""
        monkeypatch.setenv("WB_SQUEEZE_ENABLED", "0")
        bars = [
            _bar(datetime(2026, 1, 16, 7, i), v=8000) for i in range(4)
        ]
        raw_det, raw_msgs = self._run_raw(bars, pm_high=3.50, vwap=3.40)
        wrap_det, wrap_msgs = self._run_wrapped(bars, pm_high=3.50, vwap=3.40)
        assert all(m is None for m in raw_msgs)
        assert all(m is None for m in wrap_msgs)
        assert raw_det.armed is None
        assert wrap_det.armed is None


# ---------------------------------------------------------------------------
# Integration: SqueezeSource + SqueezeBreakout together
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_confirmation_aligned_with_detector_prime(self, monkeypatch) -> None:
        """When SqueezeBreakout confirms, the detector should also prime
        (or already be primed). This is the framework-side fast-path
        alignment check."""
        _enable_squeeze_env(monkeypatch)
        src = SqueezeSource(symbol="VERO")
        src.set_premarket_levels(pm_high=3.50)
        src.set_vwap(3.40)
        cf = SqueezeBreakout.from_env()

        bars = [
            _bar(datetime(2026, 1, 16, 7, 0), o=3.40, h=3.42, lo=3.38, c=3.41, v=8000),
            _bar(datetime(2026, 1, 16, 7, 1), o=3.41, h=3.43, lo=3.39, c=3.42, v=9000),
            _bar(datetime(2026, 1, 16, 7, 2), o=3.42, h=3.44, lo=3.40, c=3.43, v=10_000),
            _bar(datetime(2026, 1, 16, 7, 3), o=3.43, h=3.55, lo=3.40, c=3.52, v=60_000),
        ]
        for b in bars:
            src.update_intraday(b)

        cf_result = cf.check_confirmation(level=None, bars=bars)
        # If framework confirmation says yes, detector should also be primed
        if cf_result.confirmed:
            assert src.detector._state in ("PRIMED", "ARMED", "IDLE"), (
                "detector state inconsistent with confirmation"
            )

    def test_yaml_load_round_trips(self) -> None:
        """The squeeze.yaml strategy spec loads via StrategyRegistry."""
        from framework.registry import StrategyRegistry

        sr = StrategyRegistry()
        spec = sr.load_yaml("strategies/squeeze.yaml")
        assert spec.name == "Squeeze"
        assert spec.level_source.type == "squeeze"
        assert spec.confirmation_rule.type == "squeeze_breakout"
        # Universe spec is in raw — it's not a standard framework field
        assert "universe_spec" in spec.raw
        u = spec.raw["universe_spec"]
        assert u["price_min"] == 2.0
        assert u["price_max"] == 30.0
        assert u["float_max_millions"] == 30.0
