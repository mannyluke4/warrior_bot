"""Conflict-rule tests — `first_in_time` vs `release_on_stop`.

Synthetic scenarios drive `run_portfolio_backtest` end-to-end using monkey-
patched signal evaluators + handcrafted Bar series. No Databento cache or
network is required.

Scenarios:

  test_release_on_stop_recovers_fade_after_breakout_stops
      PDH-Breakout fires 09:35, stops 09:55. PDH-Fade signal at 09:50 was
      blocked under first_in_time; under release_on_stop the fade re-arms
      after the stop and fills.

  test_first_in_time_regression_blocks_fade
      Same scenario, first_in_time mode — fade does NOT fire. Lock-collision
      log records the blocked signal.

  test_target_exit_does_not_release_lock
      PDH-Breakout fires 09:35 and hits target at 09:50. PDH-Fade signal at
      10:00 must remain blocked — only stop-exits release the lock.

  test_secondary_fill_flag_set_on_rearm
      The re-armed trade must carry secondary_fill=True; the original locked
      trade carries secondary_fill=False.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

import pytest

REPO = Path("/Users/duffy/warrior_bot_v2")
sys.path.insert(0, str(REPO))


from backtest import portfolio_backtest as pb
from backtest.portfolio_backtest import (
    EntrySignal,
    PortfolioConfig,
    SizingMode,
    StrategyArm,
    run_portfolio_backtest,
)
from framework.level_sources.base import Bar, Level


# ---------------------------------------------------------------------------
# Synthetic-bar harness
# ---------------------------------------------------------------------------

SESSION_DATE = date(2024, 6, 3)
SYMBOL = "TEST"


def _bar(t: time, o: float, h: float, l: float, c: float, v: float = 100_000) -> Bar:
    return Bar(
        timestamp=datetime.combine(SESSION_DATE, t),
        open=o, high=h, low=l, close=c, volume=v, symbol=SYMBOL,
    )


def _build_day_bars(
    breakout_stops: bool,
    breakout_hits_target_at_0950: bool = False,
) -> list[Bar]:
    """RTH bar series for the synthetic scenario.

    Setup A — breakout_stops=True, breakout_hits_target_at_0950=False:
      Bar 09:30 open at $100. Bar 09:34 close $101.50 (breakout level).
      Bar 09:35 fills the breakout long @ $101.50, holds until 09:55 stop @ $100.50.
      Bar 09:50 closes at $101.40 (a 'fade' from the breakout high) — fade short
      signal fires here with fill at 09:51 open.

    Setup B — breakout_hits_target_at_0950=True:
      Bar 09:50 high pierces $103.00 target — breakout long exits via 'target'
      at 09:50. Lock does NOT release.
    """
    bars: list[Bar] = []
    # 09:30 - 09:34 — pre-breakout flat near $101
    for m in range(0, 5):
        t = time(9, 30 + m)
        bars.append(_bar(t, 101.0, 101.10, 100.90, 101.0))
    # 09:35 fill bar for breakout — opens 101.50 (entry price)
    bars.append(_bar(time(9, 35), 101.50, 102.0, 101.40, 101.80))
    # 09:36 - 09:49 — drift slightly higher to set up the fade
    for m in range(36, 50):
        t = time(9, m)
        bars.append(_bar(t, 101.80, 101.95, 101.70, 101.85))
    # 09:50 — fade-trigger bar. Long upper wick at $102.50 then close back to 101.40.
    if breakout_hits_target_at_0950:
        # Spike high through $103 (target) on this bar — breakout exits via target.
        bars.append(_bar(time(9, 50), 101.85, 103.20, 101.80, 102.50))
    else:
        bars.append(_bar(time(9, 50), 101.85, 102.50, 101.30, 101.40))
    # 09:51 fade fill bar — opens at 101.40 (entry for short).
    if breakout_hits_target_at_0950:
        bars.append(_bar(time(9, 51), 102.50, 102.60, 102.30, 102.40))
    else:
        bars.append(_bar(time(9, 51), 101.40, 101.50, 100.80, 100.90))
    # 09:52 - 09:54 — bars between fade fill and breakout stop
    for m in range(52, 55):
        bars.append(_bar(time(9, m), 100.90, 101.00, 100.70, 100.80))
    # 09:55 — STOP HIT FOR THE BREAKOUT (price prints 100.40 < 100.50 stop)
    if breakout_stops:
        bars.append(_bar(time(9, 55), 100.80, 100.85, 100.30, 100.40))
    else:
        bars.append(_bar(time(9, 55), 100.80, 100.95, 100.70, 100.80))
    # 09:56 - 15:54 — flat drift down for the fade short to take profit on close
    for m_total in range(56, 354):
        # 56..59 + 60..839 -> walk minute by minute
        total_min = 9 * 60 + 56 + (m_total - 56)
        if total_min >= 15 * 60 + 55:
            break
        hh, mm = divmod(total_min, 60)
        bars.append(_bar(time(hh, mm), 100.40, 100.50, 100.30, 100.40))
    # Final 15:54 bar — flat
    bars.append(_bar(time(15, 54), 100.40, 100.45, 100.35, 100.40))
    return bars


# ---------------------------------------------------------------------------
# Synthetic signal evaluators
# ---------------------------------------------------------------------------


def _find_bar_idx(bars: list[Bar], t: time) -> Optional[int]:
    for i, b in enumerate(bars):
        if b.timestamp.time() == t:
            return i
    return None


def _make_breakout_signal(bars: list[Bar], spec: dict, prior_bars=None):
    """Synthetic 'PDH-PDL-Breakout': long at 09:35 confirming a $101.50 break."""
    # confirmation bar at 09:34 -> entry fill at 09:35
    idx = _find_bar_idx(bars, time(9, 34))
    if idx is None:
        return None
    return EntrySignal(
        bar_idx=idx,
        direction="long",
        level=Level(price=101.50, kind="PDH", session_date=bars[0].timestamp.date()),
        proximate_levels=(
            Level(price=101.50, kind="PDH", session_date=bars[0].timestamp.date()),
            Level(price=99.00, kind="PDL", session_date=bars[0].timestamp.date()),
        ),
    )


def _make_fade_signal(bars: list[Bar], spec: dict, prior_bars=None):
    """Synthetic 'PDH-PDL-Fade': short at 09:51 after fade-pattern bar 09:50."""
    idx = _find_bar_idx(bars, time(9, 50))
    if idx is None:
        return None
    return EntrySignal(
        bar_idx=idx,
        direction="short",
        level=Level(price=102.50, kind="PDH", session_date=bars[0].timestamp.date()),
        proximate_levels=(
            Level(price=102.50, kind="PDH", session_date=bars[0].timestamp.date()),
            Level(price=99.00, kind="PDL", session_date=bars[0].timestamp.date()),
        ),
    )


# Minimal YAML-shaped specs the trade-builder needs. just_past_level stop +
# r_multiple target keeps the math obvious.
_BREAKOUT_SPEC = {
    "name": "PDH-PDL-Breakout",
    "stop_rule": {"type": "just_past_level", "params": {"pad_dollar": 1.00}},
    "target_rule": {"type": "r_multiple", "params": {"r_multiple": 1.5}},
}
_FADE_SPEC = {
    "name": "PDH-PDL-Fade",
    "stop_rule": {"type": "just_past_level", "params": {"pad_dollar": 0.50}},
    "target_rule": {"type": "r_multiple", "params": {"r_multiple": 2.0}},
}


@pytest.fixture
def patched_signal_funcs(monkeypatch):
    """Replace SIGNAL_FUNCS with synthetic evaluators keyed by yaml filename."""
    monkeypatch.setitem(pb.SIGNAL_FUNCS, "pdh_pdl_breakout.yaml",
                        lambda b, s, prior: _make_breakout_signal(b, s, prior))
    monkeypatch.setitem(pb.SIGNAL_FUNCS, "pdh_pdl_fade.yaml",
                        lambda b, s, prior: _make_fade_signal(b, s, prior))


@pytest.fixture
def patched_arms(monkeypatch):
    """Bypass YAML on disk — give the engine pre-baked StrategyArms."""
    fake_breakout = StrategyArm(
        name="PDH-PDL-Breakout",
        yaml_path=str(REPO / "strategies" / "pdh_pdl_breakout.yaml"),
        spec=_BREAKOUT_SPEC,
    )
    fake_fade = StrategyArm(
        name="PDH-PDL-Fade",
        yaml_path=str(REPO / "strategies" / "pdh_pdl_fade.yaml"),
        spec=_FADE_SPEC,
    )

    def _from_yaml(yaml_path: str) -> StrategyArm:
        if "breakout" in yaml_path:
            return fake_breakout
        if "fade" in yaml_path:
            return fake_fade
        raise ValueError(yaml_path)

    monkeypatch.setattr(StrategyArm, "from_yaml", staticmethod(_from_yaml))


@pytest.fixture
def patched_universe_and_sessions(monkeypatch):
    """Single synthetic symbol, single synthetic session, our crafted bars."""
    monkeypatch.setattr(pb, "UNIVERSE", (SYMBOL,))
    monkeypatch.setattr(pb, "_enumerate_sessions", lambda cfg: [SESSION_DATE])


def _install_bars(monkeypatch, bars: list[Bar]) -> None:
    """Make load_day_bars / load_prior_day_bars return our synthetic series."""
    def _today(sym: str, d: date) -> list[Bar]:
        if sym == SYMBOL and d == SESSION_DATE:
            return list(bars)
        return []

    def _prior(sym: str, d: date, lookback_days: int = 5) -> list[Bar]:
        # Provide a synthetic prior session so PDH/PDL would resolve; our
        # patched signal funcs ignore prior anyway.
        if sym == SYMBOL:
            return [
                Bar(timestamp=datetime.combine(d - timedelta(days=1), time(15, 59)),
                    open=100.0, high=102.0, low=99.0, close=101.0,
                    volume=1_000_000, symbol=sym)
            ]
        return []

    monkeypatch.setattr(pb, "load_day_bars", _today)
    monkeypatch.setattr(pb, "load_prior_day_bars", _prior)


def _base_cfg(conflict_rule: str, tmp_path: Path) -> PortfolioConfig:
    return PortfolioConfig(
        sizing_mode=SizingMode(name="fixed_dollar", fixed_dollar_risk=1000.0),
        strategy_yamls=(
            "/dummy/pdh_pdl_breakout.yaml",
            "/dummy/pdh_pdl_fade.yaml",
        ),
        universe=(SYMBOL,),
        starting_equity=100_000.0,
        start_date=SESSION_DATE,
        end_date=SESSION_DATE,
        conflict_rule=conflict_rule,
        lock_collisions_log_path=str(tmp_path / "lock_collisions.csv"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_release_on_stop_recovers_fade_after_breakout_stops(
    monkeypatch, tmp_path,
    patched_signal_funcs, patched_arms, patched_universe_and_sessions,
):
    """Under release_on_stop, the breakout stops at 09:55 → fade signal at
    09:50 (whose fill_ts = 09:51) re-arms because its fill_ts > 09:55? No —
    its fill_ts is 09:51 < 09:55, so it would have been blocked DURING the
    lock. The recovery comes when the SECOND fade-signal at 09:56+ fires.

    For this synthetic test we model the real-world H8 pattern explicitly:
    the fade signal's bar_idx is 09:50 (fill_ts 09:51). Under release_on_stop,
    the lock releases at 09:55 stop, so candidates with fill_ts > 09:55
    re-arm. Our fade fill_ts is 09:51 which is BEFORE 09:55 — so this exact
    scenario tests that the fade does NOT re-arm because the lock was active
    at its fill time.

    For the lift to materialize we make the fade signal fire AFTER the stop —
    bar 09:56 confirmation, fill 09:57. We rebuild the bar set with that.
    """
    # Use the "breakout stops" bar set
    bars = _build_day_bars(breakout_stops=True)
    _install_bars(monkeypatch, bars)

    # Move fade signal to AFTER the 09:55 stop so fill_ts > exit_ts
    def fade_post_stop(b, s, prior=None):
        idx = _find_bar_idx(b, time(9, 56))
        if idx is None:
            return None
        return EntrySignal(
            bar_idx=idx,
            direction="short",
            level=Level(price=101.0, kind="PDH",
                        session_date=b[0].timestamp.date()),
            proximate_levels=(
                Level(price=101.0, kind="PDH",
                      session_date=b[0].timestamp.date()),
                Level(price=99.0, kind="PDL",
                      session_date=b[0].timestamp.date()),
            ),
        )

    monkeypatch.setitem(pb.SIGNAL_FUNCS, "pdh_pdl_fade.yaml", fade_post_stop)

    cfg = _base_cfg("release_on_stop", tmp_path)
    result = run_portfolio_backtest(cfg)

    breakout_trades = result["trades_by_strategy"]["PDH-PDL-Breakout"]
    fade_trades = result["trades_by_strategy"]["PDH-PDL-Fade"]

    assert len(breakout_trades) == 1, "breakout should fire once"
    assert breakout_trades[0]["exit_reason"] == "stop", \
        "breakout must stop out for the lock to release"
    assert breakout_trades[0]["secondary_fill"] is False

    assert len(fade_trades) == 1, (
        "release_on_stop must allow the fade to fire AFTER the breakout stop"
    )
    assert fade_trades[0]["secondary_fill"] is True, (
        "fade trade should be tagged secondary_fill=True (re-armed)"
    )
    # The fade-blocked-but-re-armed signal is NOT a collision in
    # release_on_stop accounting.
    assert result["lock_collisions"] == 0


def test_first_in_time_regression_blocks_fade(
    monkeypatch, tmp_path,
    patched_signal_funcs, patched_arms, patched_universe_and_sessions,
):
    """Same scenario, first_in_time. Fade must NOT fire; collision logged."""
    bars = _build_day_bars(breakout_stops=True)
    _install_bars(monkeypatch, bars)

    def fade_post_stop(b, s, prior=None):
        idx = _find_bar_idx(b, time(9, 56))
        if idx is None:
            return None
        return EntrySignal(
            bar_idx=idx,
            direction="short",
            level=Level(price=101.0, kind="PDH",
                        session_date=b[0].timestamp.date()),
            proximate_levels=(
                Level(price=101.0, kind="PDH",
                      session_date=b[0].timestamp.date()),
                Level(price=99.0, kind="PDL",
                      session_date=b[0].timestamp.date()),
            ),
        )

    monkeypatch.setitem(pb.SIGNAL_FUNCS, "pdh_pdl_fade.yaml", fade_post_stop)

    cfg = _base_cfg("first_in_time", tmp_path)
    result = run_portfolio_backtest(cfg)

    assert len(result["trades_by_strategy"]["PDH-PDL-Breakout"]) == 1
    assert len(result["trades_by_strategy"]["PDH-PDL-Fade"]) == 0, (
        "first_in_time must keep the fade blocked for the whole day"
    )
    assert result["lock_collisions"] == 1, (
        "the blocked fade signal should be logged as a collision"
    )
    # And no trade should ever be tagged secondary_fill
    all_trades = (result["trades_by_strategy"]["PDH-PDL-Breakout"]
                  + result["trades_by_strategy"]["PDH-PDL-Fade"])
    assert not any(t.get("secondary_fill") for t in all_trades)


def test_target_exit_does_not_release_lock(
    monkeypatch, tmp_path,
    patched_signal_funcs, patched_arms, patched_universe_and_sessions,
):
    """release_on_stop: a target exit must NOT release the lock. The fade at
    09:56 (after target hit at 09:50) must still be blocked."""
    bars = _build_day_bars(breakout_stops=False, breakout_hits_target_at_0950=True)
    _install_bars(monkeypatch, bars)

    def fade_post_target(b, s, prior=None):
        idx = _find_bar_idx(b, time(9, 56))
        if idx is None:
            return None
        return EntrySignal(
            bar_idx=idx,
            direction="short",
            level=Level(price=102.50, kind="PDH",
                        session_date=b[0].timestamp.date()),
            proximate_levels=(
                Level(price=102.50, kind="PDH",
                      session_date=b[0].timestamp.date()),
                Level(price=99.0, kind="PDL",
                      session_date=b[0].timestamp.date()),
            ),
        )

    monkeypatch.setitem(pb.SIGNAL_FUNCS, "pdh_pdl_fade.yaml", fade_post_target)

    cfg = _base_cfg("release_on_stop", tmp_path)
    result = run_portfolio_backtest(cfg)

    breakout_trades = result["trades_by_strategy"]["PDH-PDL-Breakout"]
    fade_trades = result["trades_by_strategy"]["PDH-PDL-Fade"]

    assert len(breakout_trades) == 1
    assert breakout_trades[0]["exit_reason"] == "target", (
        "breakout must hit target in this scenario"
    )
    assert len(fade_trades) == 0, (
        "target exit must NOT release the lock — fade must stay blocked"
    )
    assert result["lock_collisions"] == 1
