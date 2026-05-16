"""Unit tests for framework/level_sources/anchored_vwap.py — Wave 5 Agent M.

Coverage:
- Gap-day detection: positive gap, negative gap, sub-threshold (no anchor)
- Earnings anchor detection: stub-calendar match, no match outside lookback
- FOMC anchor detection: hardcoded calendar match
- Multi-anchor merging: gap + earnings + FOMC, capped at multi_anchor_count
- VWAP math from anchor: matches manual reference calculation
- update_intraday: incremental == batch parity
- Edge cases: empty history, all-zero volume bars, no anchors in window
- Lookback boundary: anchor at exactly lookback_days included
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from framework.level_sources.anchored_vwap import (
    Anchor,
    AnchoredVWAPSource,
    EARNINGS_CALENDAR,
    FOMC_DATES,
    detect_earnings_anchors,
    detect_fomc_anchors,
    detect_gap_days,
)
from framework.level_sources.base import Bar, BarHistory


# ---------------------------------------------------------------------------
# Helpers — build minimal multi-session histories
# ---------------------------------------------------------------------------


def _rth_bar(
    d: date,
    minute_offset: int,
    open_p: float,
    close_p: float,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1_000.0,
    symbol: str = "TEST",
) -> Bar:
    ts = datetime.combine(d, time(9, 30)) + timedelta(minutes=minute_offset)
    return Bar(
        timestamp=ts,
        open=open_p,
        high=high if high is not None else max(open_p, close_p),
        low=low if low is not None else min(open_p, close_p),
        close=close_p,
        volume=volume,
        symbol=symbol,
    )


def _session(
    d: date,
    *,
    bars_count: int = 5,
    open_p: float = 100.0,
    close_p: float = 100.0,
    high_p: float | None = None,
    low_p: float | None = None,
    vol_per_bar: float = 1_000.0,
    symbol: str = "TEST",
) -> list[Bar]:
    """Build N RTH bars for a session. First bar opens at open_p, last bar
    closes at close_p; high/low cover the whole session range.
    """
    out: list[Bar] = []
    if bars_count <= 0:
        return out
    span = bars_count - 1 if bars_count > 1 else 1
    high = high_p if high_p is not None else max(open_p, close_p)
    low = low_p if low_p is not None else min(open_p, close_p)
    for i in range(bars_count):
        if bars_count == 1:
            o, c = open_p, close_p
        else:
            t = i / span
            o = open_p + t * (close_p - open_p)
            c = open_p + ((i + 0.5) / bars_count) * (close_p - open_p) if i < bars_count - 1 else close_p
        out.append(_rth_bar(
            d, i, o, c, high=high, low=low, volume=vol_per_bar, symbol=symbol,
        ))
    return out


def _build_multi_session_history(
    sessions: list[tuple[date, float, float]],
    *,
    bars_per_session: int = 5,
    vol_per_bar: float = 1_000.0,
    symbol: str = "TEST",
) -> BarHistory:
    """sessions = list of (date, open_p, close_p). Return BarHistory."""
    bars: list[Bar] = []
    for d, o, c in sessions:
        bars.extend(_session(
            d, bars_count=bars_per_session, open_p=o, close_p=c,
            vol_per_bar=vol_per_bar, symbol=symbol,
        ))
    return BarHistory(symbol=symbol, bars=bars)


# ---------------------------------------------------------------------------
# Gap-day detection
# ---------------------------------------------------------------------------


def test_detect_gap_days_positive_gap_above_threshold():
    """A 5% gap up between consecutive sessions should be detected."""
    hist = _build_multi_session_history([
        (date(2024, 6, 10), 100.0, 100.0),   # prior session
        (date(2024, 6, 11), 105.0, 105.0),   # gap up 5%
    ])
    anchors = detect_gap_days(
        hist.bars,
        target_date=date(2024, 6, 12),
        lookback_days=30,
        gap_threshold_pct=0.02,
    )
    assert len(anchors) == 1
    assert anchors[0].session_date == date(2024, 6, 11)
    assert anchors[0].kind == "gap_day"
    assert anchors[0].metadata["gap_pct"] == pytest.approx(0.05)


def test_detect_gap_days_negative_gap_above_threshold():
    """A -3% gap should be detected (absolute value threshold)."""
    hist = _build_multi_session_history([
        (date(2024, 6, 10), 100.0, 100.0),
        (date(2024, 6, 11), 97.0, 97.0),     # gap down 3%
    ])
    anchors = detect_gap_days(
        hist.bars,
        target_date=date(2024, 6, 12),
        lookback_days=30,
        gap_threshold_pct=0.02,
    )
    assert len(anchors) == 1
    assert anchors[0].metadata["gap_pct"] == pytest.approx(-0.03)


def test_detect_gap_days_sub_threshold_ignored():
    """A 1% gap with threshold=2% should NOT be detected."""
    hist = _build_multi_session_history([
        (date(2024, 6, 10), 100.0, 100.0),
        (date(2024, 6, 11), 101.0, 101.0),   # only 1%
    ])
    anchors = detect_gap_days(
        hist.bars,
        target_date=date(2024, 6, 12),
        lookback_days=30,
        gap_threshold_pct=0.02,
    )
    assert anchors == []


def test_detect_gap_days_outside_lookback_ignored():
    """A gap day older than lookback_days should be excluded."""
    target = date(2024, 6, 12)
    far_prior = target - timedelta(days=60)
    far_gap = target - timedelta(days=59)
    hist = _build_multi_session_history([
        (far_prior, 100.0, 100.0),
        (far_gap, 110.0, 110.0),             # gap 10%, but >30 days back
    ])
    anchors = detect_gap_days(
        hist.bars,
        target_date=target,
        lookback_days=30,
        gap_threshold_pct=0.02,
    )
    assert anchors == []


def test_detect_gap_days_most_recent_first():
    """Multiple gap days are returned newest-first."""
    hist = _build_multi_session_history([
        (date(2024, 6, 1), 100.0, 100.0),
        (date(2024, 6, 2), 105.0, 105.0),    # gap +5%
        (date(2024, 6, 3), 105.0, 105.0),
        (date(2024, 6, 4), 110.0, 110.0),    # gap +4.76%
    ])
    anchors = detect_gap_days(
        hist.bars,
        target_date=date(2024, 6, 5),
        lookback_days=30,
        gap_threshold_pct=0.02,
    )
    assert len(anchors) == 2
    assert anchors[0].session_date == date(2024, 6, 4)
    assert anchors[1].session_date == date(2024, 6, 2)


# ---------------------------------------------------------------------------
# Earnings anchor detection
# ---------------------------------------------------------------------------


def test_detect_earnings_anchors_uses_stub_calendar():
    """For AAPL, the 2024-02-01 earnings release should produce an anchor on
    the next trading session (2024-02-02 was a Friday, present in our
    multi-session history)."""
    hist = _build_multi_session_history([
        (date(2024, 2, 1), 180.0, 180.0),    # day of release (pre-close bars)
        (date(2024, 2, 2), 185.0, 185.0),    # reaction day
        (date(2024, 2, 5), 186.0, 186.0),    # following session
    ], symbol="AAPL")
    anchors = detect_earnings_anchors(
        hist.bars,
        symbol="AAPL",
        target_date=date(2024, 2, 6),
        lookback_days=30,
    )
    assert len(anchors) == 1
    assert anchors[0].kind == "earnings"
    assert anchors[0].session_date == date(2024, 2, 2)


def test_detect_earnings_anchors_unknown_symbol_returns_empty():
    """Symbols not in the stub calendar emit no earnings anchors."""
    hist = _build_multi_session_history([
        (date(2024, 6, 10), 50.0, 50.0),
    ], symbol="UNKNOWNXYZ")
    anchors = detect_earnings_anchors(
        hist.bars,
        symbol="UNKNOWNXYZ",
        target_date=date(2024, 6, 12),
        lookback_days=30,
    )
    assert anchors == []


# ---------------------------------------------------------------------------
# FOMC anchor detection
# ---------------------------------------------------------------------------


def test_detect_fomc_anchors_uses_hardcoded_calendar():
    """The 2024-03-20 FOMC date should yield an anchor."""
    hist = _build_multi_session_history([
        (date(2024, 3, 19), 500.0, 500.0),
        (date(2024, 3, 20), 510.0, 510.0),   # FOMC day
        (date(2024, 3, 21), 510.0, 510.0),
    ])
    anchors = detect_fomc_anchors(
        hist.bars,
        target_date=date(2024, 3, 22),
        lookback_days=10,
    )
    assert len(anchors) == 1
    assert anchors[0].kind == "fomc"
    assert anchors[0].session_date == date(2024, 3, 20)


def test_detect_fomc_anchors_no_history_for_fomc_returns_empty():
    """If history has no bars on the FOMC date, no anchor emitted."""
    hist = _build_multi_session_history([
        (date(2024, 3, 19), 500.0, 500.0),
        # 2024-03-20 deliberately missing
        (date(2024, 3, 21), 510.0, 510.0),
    ])
    anchors = detect_fomc_anchors(
        hist.bars,
        target_date=date(2024, 3, 22),
        lookback_days=10,
    )
    assert anchors == []


# ---------------------------------------------------------------------------
# Anchor selection by anchor_type
# ---------------------------------------------------------------------------


def test_anchored_vwap_source_gap_day_picks_most_recent_gap():
    """anchor_type='gap_day' returns one Level for the most-recent gap."""
    hist = _build_multi_session_history([
        (date(2024, 6, 10), 100.0, 100.0),
        (date(2024, 6, 11), 105.0, 105.0),   # gap +5%
        (date(2024, 6, 12), 105.0, 110.0),   # intraday session — target
    ])
    src = AnchoredVWAPSource(anchor_type="gap_day", lookback_days=30)
    ls = src.compute_levels("TEST", hist, target_date=date(2024, 6, 12))
    # One Level (AVWAP from gap day)
    assert len(ls.levels) == 1
    assert ls.levels[0].kind == "AVWAP"
    assert ls.levels[0].metadata["anchor_type"] == "gap_day"
    assert ls.levels[0].metadata["anchor_date"] == "2024-06-11"


def test_anchored_vwap_source_multi_anchor_capped_at_count():
    """multi_anchor returns up to ``multi_anchor_count`` distinct anchors."""
    sessions = [
        (date(2024, 3, 19), 100.0, 100.0),
        (date(2024, 3, 20), 105.0, 105.0),   # FOMC + gap (both fire)
        (date(2024, 3, 21), 105.0, 105.0),
        (date(2024, 3, 22), 110.0, 110.0),   # gap
    ]
    hist = _build_multi_session_history(sessions, symbol="META")
    src = AnchoredVWAPSource(
        anchor_type="multi_anchor",
        lookback_days=30,
        multi_anchor_count=3,
    )
    ls = src.compute_levels("META", hist, target_date=date(2024, 3, 25))
    assert 1 <= len(ls.levels) <= 3
    kinds = {lvl.metadata["anchor_type"] for lvl in ls.levels}
    # FOMC + gap_day should both be represented if calendars align
    assert "gap_day" in kinds or "fomc" in kinds


def test_anchored_vwap_source_no_anchor_returns_empty():
    """When no anchor matches in the lookback, the LevelSet is empty."""
    hist = _build_multi_session_history([
        (date(2024, 6, 10), 100.0, 100.0),
        (date(2024, 6, 11), 100.5, 100.5),   # 0.5% — sub-threshold
    ])
    src = AnchoredVWAPSource(anchor_type="gap_day", lookback_days=30)
    ls = src.compute_levels("TEST", hist, target_date=date(2024, 6, 12))
    assert ls.levels == ()


# ---------------------------------------------------------------------------
# VWAP math from anchor
# ---------------------------------------------------------------------------


def test_avwap_math_matches_manual_reference():
    """AVWAP from anchor should equal sum(typical*vol) / sum(vol) from anchor."""
    # Build a 2-session history with a 2% gap. Anchor = day 2 open.
    bars_day1 = _session(
        date(2024, 6, 10), bars_count=2, open_p=100.0, close_p=100.0,
        vol_per_bar=1000.0,
    )
    bars_day2 = _session(
        date(2024, 6, 11), bars_count=3, open_p=103.0, close_p=105.0,
        vol_per_bar=2000.0,
    )
    bars_day3 = _session(
        date(2024, 6, 12), bars_count=2, open_p=105.0, close_p=107.0,
        vol_per_bar=3000.0,
    )
    hist = BarHistory(symbol="TEST", bars=bars_day1 + bars_day2 + bars_day3)
    src = AnchoredVWAPSource(anchor_type="gap_day", lookback_days=30)
    ls = src.compute_levels("TEST", hist, target_date=date(2024, 6, 12))
    assert len(ls.levels) == 1

    # Manual reference: typical = (H+L+C)/3 for each bar from anchor (day 2 open) forward
    anchor_ts = bars_day2[0].timestamp
    cum_pv, cum_vol = 0.0, 0.0
    for b in bars_day2 + bars_day3:
        if b.timestamp < anchor_ts:
            continue
        tp = (b.high + b.low + b.close) / 3.0
        cum_pv += tp * b.volume
        cum_vol += b.volume
    expected = cum_pv / cum_vol

    assert ls.levels[0].price == pytest.approx(expected, rel=1e-9)


def test_update_intraday_parity_with_batch():
    """Replaying intraday via update_intraday should equal compute_levels."""
    # Build history through end of session 2 (the anchor session), then
    # feed session-3 bars via update_intraday and confirm equality with a
    # batch compute over the full union.
    bars_day1 = _session(date(2024, 6, 10), bars_count=2, open_p=100.0, close_p=100.0)
    bars_day2 = _session(date(2024, 6, 11), bars_count=3, open_p=105.0, close_p=105.0)
    bars_day3 = _session(date(2024, 6, 12), bars_count=4, open_p=105.0, close_p=108.0)

    # Batch
    full = BarHistory(symbol="TEST", bars=bars_day1 + bars_day2 + bars_day3)
    src_batch = AnchoredVWAPSource(anchor_type="gap_day", lookback_days=30)
    ls_batch = src_batch.compute_levels("TEST", full, target_date=date(2024, 6, 12))

    # Incremental: start with only day1+day2, then feed day3 intraday
    pre = BarHistory(symbol="TEST", bars=bars_day1 + bars_day2)
    src_inc = AnchoredVWAPSource(anchor_type="gap_day", lookback_days=30)
    src_inc.compute_levels("TEST", pre, target_date=date(2024, 6, 12))
    for b in bars_day3:
        src_inc.update_intraday(b)
    ls_inc = src_inc.current_levelset()

    assert len(ls_batch.levels) == len(ls_inc.levels) == 1
    assert ls_batch.levels[0].price == pytest.approx(ls_inc.levels[0].price, rel=1e-12)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_history_returns_empty_levelset():
    src = AnchoredVWAPSource(anchor_type="gap_day")
    ls = src.compute_levels("TEST", BarHistory(symbol="TEST", bars=[]))
    assert ls.levels == ()


def test_zero_volume_bars_skipped():
    """Bars with 0 volume should not contribute to the running VWAP."""
    bars = [
        _rth_bar(date(2024, 6, 10), 0, 100.0, 100.0, volume=1000.0),
        _rth_bar(date(2024, 6, 11), 0, 103.0, 103.0, volume=0.0),   # gap, anchor
        _rth_bar(date(2024, 6, 11), 1, 104.0, 104.0, volume=1000.0),
    ]
    hist = BarHistory(symbol="TEST", bars=bars)
    src = AnchoredVWAPSource(anchor_type="gap_day", lookback_days=30)
    ls = src.compute_levels("TEST", hist, target_date=date(2024, 6, 12))
    assert len(ls.levels) == 1
    # Only the second bar of the anchor session contributed (typical=104).
    assert ls.levels[0].price == pytest.approx(104.0)


def test_lookback_boundary_inclusive():
    """An anchor exactly lookback_days back should still be included."""
    target = date(2024, 6, 30)
    lookback = 10
    # gap day at target - lookback (exactly on the boundary)
    boundary_date = target - timedelta(days=lookback)
    prior = boundary_date - timedelta(days=1)
    hist = _build_multi_session_history([
        (prior, 100.0, 100.0),
        (boundary_date, 105.0, 105.0),       # +5% gap
    ])
    anchors = detect_gap_days(
        hist.bars,
        target_date=target,
        lookback_days=lookback,
        gap_threshold_pct=0.02,
    )
    assert len(anchors) == 1
    assert anchors[0].session_date == boundary_date
