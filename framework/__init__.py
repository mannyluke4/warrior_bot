"""Healthy Fluctuation Framework.

A unified level-reaction primitive for the warrior_bot trading system.

Every strategy in this framework is one instance of the core primitive:

    strategy = (level_source, arrival_detector, confirmation_rule,
                stop_rule, target_rule)

See DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md for the full architecture.

This is Wave 1 scaffolding — protocols and value objects only.
Wave 2 adds the actual level computation and confirmation patterns.
The framework lives entirely under framework/ and tests/framework/.
Existing live code (bot_v3_hybrid.py, squeeze_detector_v2.py, etc.) is
NOT touched by this build.
"""

from __future__ import annotations

from framework.sizing import HalfKellySizer
from framework.risk import RiskManager, RiskConfig, StrategyRiskState
from framework.attribution import StrategyAttribution, TradeRecord
from framework.vix_regime import (
    VIXRegime,
    REGIME_LOW,
    REGIME_OPTIMAL,
    REGIME_HIGH,
    REGIME_EXTREME,
)

__version__ = "0.1.0-wave1-skeleton"
__all__ = [
    "__version__",
    "HalfKellySizer",
    "RiskManager",
    "RiskConfig",
    "StrategyRiskState",
    "StrategyAttribution",
    "TradeRecord",
    "VIXRegime",
    "REGIME_LOW",
    "REGIME_OPTIMAL",
    "REGIME_HIGH",
    "REGIME_EXTREME",
]
