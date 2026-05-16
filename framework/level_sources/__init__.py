"""Level source plugins for the healthy-fluctuation framework.

Each plugin implements LevelSourceProtocol and produces a LevelSet given
a symbol + bar history. Built-ins land in Wave 2 (opening_range, vwap,
pdh_pdl, round_number, volume_profile, etc.).
"""
from __future__ import annotations

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelKind,
    LevelSet,
    LevelSourceProtocol,
)
from framework.level_sources.pdh_pdl import PDHPDLSource
from framework.level_sources.squeeze import SqueezeSource
from framework.level_sources.vwap import SlopeRegime, VWAPSource, VWAPState

__all__ = [
    "Bar",
    "BarHistory",
    "Level",
    "LevelKind",
    "LevelSet",
    "LevelSourceProtocol",
    "PDHPDLSource",
    "SqueezeSource",
    "SlopeRegime",
    "VWAPSource",
    "VWAPState",
]
