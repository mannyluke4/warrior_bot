"""Main-bot strategy filters ported from the sub-bots (2026-06-17 plan):
  - 70%-equity sizing (WB_EQUITY_PCT) — verified by parity with the sub-bot impl
    and the VERO regression (unchanged when off); the sizing override is inline in
    enter_trade so it's covered by integration, not unit-tested here.
  - entry time-window block (WB_ENTRY_BLOCK_WINDOWS_ET)
  - per-symbol same-day loss-lockout (WB_SYMBOL_LOSS_LOCKOUT)

Env vars must be set BEFORE importing the module (read at import time).
Run: ./venv/bin/python tests/test_mainbot_filters.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WB_EQUITY_PCT"] = "0.70"
os.environ["WB_ENTRY_BLOCK_WINDOWS_ET"] = "09:30-11:00,13:00-14:00"
os.environ["WB_SYMBOL_LOSS_LOCKOUT"] = "1"
import bot_v3_hybrid as b
from datetime import datetime as _dt


def test_config_parsed():
    assert b.ENTRY_BLOCK_WINDOWS == [(570, 660), (780, 840)]
    assert b.EQUITY_PCT_SIZING == 0.70
    assert b.SYMBOL_LOSS_LOCKOUT is True


def _patch_time(h, mi):
    class FakeDT:
        @staticmethod
        def now(tz=None):
            return _dt(2026, 6, 18, h, mi, tzinfo=tz)
    b.datetime = FakeDT


def test_loss_lockout():
    _patch_time(12, 0)            # clear window
    b.state._lossout_symbols = set()
    assert b._strategy_filters_block("CRVO", "move_strike") is False
    b.state._lossout_symbols = {"CRVO"}
    assert b._strategy_filters_block("CRVO", "move_strike") is True    # locked
    assert b._strategy_filters_block("WXYZ", "move_strike") is False   # not locked


def test_time_window_block():
    b.state._lossout_symbols = set()
    _patch_time(10, 0)           # inside 9:30-11:00
    assert b._strategy_filters_block("CRVO", "move_strike") is True
    _patch_time(13, 30)          # inside 13:00-14:00
    assert b._strategy_filters_block("CRVO", "move_strike") is True
    _patch_time(12, 0)           # clear
    assert b._strategy_filters_block("CRVO", "move_strike") is False


def test_time_window_block_gates_on_arm_time():
    b.state._lossout_symbols = set()
    # Armed valid (08:48=528), trigger fires inside 9:30-11:00 block → ALLOW.
    b.state._arm_minute_et = {"NXTS": 528}
    _patch_time(10, 0)
    assert b._strategy_filters_block("NXTS", "move_strike") is False
    # New setup armed inside the window (10:00=600) → BLOCK.
    b.state._arm_minute_et["LATE"] = 600
    _patch_time(10, 5)
    assert b._strategy_filters_block("LATE", "move_strike") is True
    # No arm stamp → fall back to current time (in block) → BLOCK.
    b.state._arm_minute_et = {}
    _patch_time(10, 0)
    assert b._strategy_filters_block("ZZZZ", "move_strike") is True


if __name__ == "__main__":
    test_config_parsed()
    test_loss_lockout()
    test_time_window_block()
    test_time_window_block_gates_on_arm_time()
    print("ALL MAIN-BOT FILTER TESTS PASSED")
