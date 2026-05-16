"""Unit tests for framework.vix_regime.VIXRegime."""
from __future__ import annotations

import os

import pytest

from framework.vix_regime import (
    VIXRegime,
    REGIME_LOW,
    REGIME_OPTIMAL,
    REGIME_HIGH,
    REGIME_EXTREME,
)


class TestVIXRegimeClassification:
    @pytest.mark.parametrize(
        "vix,expected",
        [
            (5.0, REGIME_LOW),
            (10.0, REGIME_LOW),
            (15.99, REGIME_LOW),
            (16.0, REGIME_OPTIMAL),
            (20.0, REGIME_OPTIMAL),
            (27.99, REGIME_OPTIMAL),
            (28.0, REGIME_HIGH),
            (35.0, REGIME_HIGH),
            (39.99, REGIME_HIGH),
            (40.0, REGIME_EXTREME),
            (60.0, REGIME_EXTREME),
            (100.0, REGIME_EXTREME),
        ],
    )
    def test_regime_labels(self, vix: float, expected: str):
        r = VIXRegime(enabled=False)  # enabled flag doesn't affect classify
        assert r.current_regime(vix) == expected

    def test_nan_defaults_to_optimal(self):
        r = VIXRegime(enabled=False)
        assert r.current_regime(float("nan")) == REGIME_OPTIMAL

    def test_string_input_defaults_to_optimal(self):
        r = VIXRegime(enabled=False)
        assert r.current_regime("not-a-number") == REGIME_OPTIMAL  # type: ignore[arg-type]


class TestVIXRegimeSizeMultiplier:
    def test_disabled_returns_base_size(self):
        r = VIXRegime(enabled=False)
        # Even extreme VIX shouldn't change size when disabled
        assert r.size_multiplier(vix_value=80.0, base_size=1000) == 1000
        assert r.size_multiplier(vix_value=5.0, base_size=500) == 500

    def test_enabled_optimal(self):
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=20.0, base_size=1000) == 1000

    def test_enabled_low(self):
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=10.0, base_size=1000) == 500

    def test_enabled_high(self):
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=35.0, base_size=1000) == 750

    def test_enabled_extreme_zeroes_size(self):
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=60.0, base_size=1000) == 0

    def test_zero_base_size_returns_zero(self):
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=20.0, base_size=0) == 0

    def test_negative_base_size_returns_zero(self):
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=20.0, base_size=-500) == 0

    def test_fractional_base_size_floored(self):
        """0.75 × 999 = 749.25 → floor to 749."""
        r = VIXRegime(enabled=True)
        assert r.size_multiplier(vix_value=35.0, base_size=999) == 749


class TestVIXRegimeEnvDefault:
    def test_default_disabled_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("WB_USE_VIX_REGIME", raising=False)
        r = VIXRegime()
        assert r.enabled is False
        # Extreme VIX with default config → still base_size (disabled)
        assert r.size_multiplier(60.0, 1000) == 1000

    def test_env_one_enables(self, monkeypatch):
        monkeypatch.setenv("WB_USE_VIX_REGIME", "1")
        r = VIXRegime()
        assert r.enabled is True

    def test_env_zero_disables(self, monkeypatch):
        monkeypatch.setenv("WB_USE_VIX_REGIME", "0")
        r = VIXRegime()
        assert r.enabled is False

    def test_explicit_enabled_overrides_env(self, monkeypatch):
        monkeypatch.setenv("WB_USE_VIX_REGIME", "1")
        r = VIXRegime(enabled=False)
        assert r.enabled is False


class TestVIXRegimeGetVIXValue:
    def test_disabled_returns_none(self):
        r = VIXRegime(enabled=False)
        assert r.get_vix_value() is None

    def test_enabled_no_databento_returns_none(self, monkeypatch):
        # Even when enabled, the scaffold returns None until Wave 4 wires
        # a real source. Test that no exception is raised.
        r = VIXRegime(enabled=True)
        v = r.get_vix_value()
        # Either databento is unavailable (None) or scaffold returns None.
        assert v is None


class TestVIXRegimeCustomRange:
    def test_custom_optimal_range(self):
        r = VIXRegime(enabled=False, optimal_range=(12.0, 24.0))
        assert r.current_regime(11.9) == REGIME_LOW
        assert r.current_regime(12.0) == REGIME_OPTIMAL
        assert r.current_regime(23.9) == REGIME_OPTIMAL
        assert r.current_regime(24.0) == REGIME_HIGH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
