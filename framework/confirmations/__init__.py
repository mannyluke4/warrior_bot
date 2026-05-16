"""Confirmation plugins for the healthy-fluctuation framework.

Each plugin implements ConfirmationProtocol and verifies whether a level
reaction is real (signal candle, breakout candle, acceptance, rejection,
L2 confirmation, etc.).
"""
from __future__ import annotations

from framework.confirmations.base import (
    ConfirmationProtocol,
    ConfirmationResult,
)
from framework.confirmations.acceptance import Acceptance
from framework.confirmations.breakout_candle import BreakoutCandle
from framework.confirmations.l2_confirm import L2Confirm
from framework.confirmations.rejection import Rejection
from framework.confirmations.signal_candle import SignalCandle
from framework.confirmations.volume_confirm import VolumeConfirm

__all__ = [
    "ConfirmationProtocol",
    "ConfirmationResult",
    "Acceptance",
    "BreakoutCandle",
    "L2Confirm",
    "Rejection",
    "SignalCandle",
    "VolumeConfirm",
]
