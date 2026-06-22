"""Sub-bot strategy filters (2026-06-17 live-validation plan):
  - 70%-equity sizing (compounds with realized daily P&L)
  - entry time-window block (cash open 9:30-11:00 + 1pm dead hour 13:00-14:00)
  - per-symbol same-day loss-lockout (kills revenge re-entries, keeps win-continuations)

Env vars must be set BEFORE importing the module (read at import time).
Run: ./venv/bin/python tests/test_subbot_filters.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WB_SUBBOT_EQUITY_PCT"] = "0.70"
os.environ["WB_ENTRY_BLOCK_WINDOWS_ET"] = "09:30-11:00,13:00-14:00"
os.environ["WB_SYMBOL_LOSS_LOCKOUT"] = "1"
import move_strike_subbot as m
from types import SimpleNamespace


def test_equity_pct_sizing_compounds():
    f = SimpleNamespace(_starting_equity=3000.0, daily_pnl=0.0)
    assert m.MoveStrikeSubBot._compute_qty(f, 5.0, 0.5, 11) == 420   # 0.7*3000/5
    f.daily_pnl = 300.0
    assert m.MoveStrikeSubBot._compute_qty(f, 5.0, 0.5, 11) == 462   # compounds up (0.7*3300/5)
    f.daily_pnl = -500.0
    assert m.MoveStrikeSubBot._compute_qty(f, 5.0, 0.5, 11) == 350   # shrinks (0.7*2500/5)
    f._starting_equity = 0.0; f.daily_pnl = 0.0
    assert m.MoveStrikeSubBot._compute_qty(f, 5.0, 0.5, 11) == 0     # no equity → skip, don't mis-size


def test_time_window_block():
    # No arm stamp → falls back to current time (legacy behavior preserved).
    g = SimpleNamespace(_entry_block_windows=[(570, 660), (780, 840)],
                        _lossout_symbols=set(), _arm_minute_et={})
    m.now_minute_et = lambda: 600   # 10:00 ET — inside open block
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "CRVO", "move_strike") is True
    m.now_minute_et = lambda: 810   # 13:30 ET — inside 1pm block
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "CRVO", "move_strike") is True
    m.now_minute_et = lambda: 720   # 12:00 ET — clear
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "CRVO", "move_strike") is False


def test_time_window_block_gates_on_arm_time():
    # The NXTS case: armed 08:48 (528, valid) but trigger fires at 10:00 (in block).
    # Gate on arm time → ALLOW (it's a setup from a valid window).
    g = SimpleNamespace(_entry_block_windows=[(570, 660), (780, 840)],
                        _lossout_symbols=set(), _arm_minute_et={"NXTS": 528})
    m.now_minute_et = lambda: 600   # 10:00 ET — inside block, but arm was valid
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "NXTS", "move_strike") is False
    # A NEW setup that armed inside the window (10:00) → BLOCK.
    g._arm_minute_et["LATE"] = 600
    m.now_minute_et = lambda: 605
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "LATE", "move_strike") is True
    # Armed valid, trigger also valid → ALLOW.
    g._arm_minute_et["MID"] = 720
    m.now_minute_et = lambda: 730
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "MID", "move_strike") is False


def test_loss_lockout():
    g = SimpleNamespace(_entry_block_windows=[], _lossout_symbols={"CRVO"})
    m.now_minute_et = lambda: 720
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "CRVO", "regime_shift") is True   # locked
    assert m.MoveStrikeSubBot._strategy_filters_block(g, "WXYZ", "regime_shift") is False  # not locked


if __name__ == "__main__":
    test_equity_pct_sizing_compounds()
    test_time_window_block()
    test_time_window_block_gates_on_arm_time()
    test_loss_lockout()
    print("ALL SUBBOT FILTER TESTS PASSED")
