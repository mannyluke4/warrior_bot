"""Unit tests for framework.level_sources.pdh_pdl.PDHPDLSource.

Coverage:
- PDH/PDL extraction correctness (basic happy path)
- Empty history / no prior session edge cases
- Multiple prior sessions: most-recent prior wins
- RTH boundary handling (09:30 inclusive, 16:00 exclusive)
- Extended-hours bars are ignored (PM and AH)
- Pathological data: PDH < PDL refused
- Holiday / weekend gap handling
- Staleness gate: > max_gap_days returns empty LevelSet
- update_intraday is a no-op
- Per-bar arrival detection edge cases (integration with ArrivalDetector)
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from framework.arrival import ArrivalDetector
from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.pdh_pdl import PDHPDLSource


# ---------------------------------------------------------------------------
# Helpers — synthetic bar builders. ET-naive timestamps per framework
# convention. RTH = 09:30:00..15:59:59.
# ---------------------------------------------------------------------------


def _bar(
    d: date,
    t: time,
    *,
    o: float = 100.0,
    h: float = 100.5,
    lo: float = 99.5,
    c: float = 100.0,
    v: float = 1000.0,
    symbol: str = "TEST",
) -> Bar:
    return Bar(
        timestamp=datetime.combine(d, t),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=v,
        symbol=symbol,
    )


def _session(
    d: date,
    *,
    hi: float = 110.0,
    lo: float = 90.0,
    symbol: str = "TEST",
) -> list[Bar]:
    """A minimal RTH session: opening bar, mid-bar (high), end-bar (low), close bar."""
    return [
        _bar(d, time(9, 30), o=100, h=101, lo=99, c=100.5, symbol=symbol),
        _bar(d, time(11, 0), o=100.5, h=hi, lo=100, c=hi - 0.5, symbol=symbol),
        _bar(d, time(14, 0), o=hi - 0.5, h=hi - 0.5, lo=lo, c=lo + 0.5, symbol=symbol),
        _bar(d, time(15, 59), o=lo + 0.5, h=lo + 1.0, lo=lo, c=lo + 0.5, symbol=symbol),
    ]


def _history(bars: list[Bar], symbol: str = "TEST") -> BarHistory:
    return BarHistory(symbol=symbol, bars=bars)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_basic_pdh_pdl_extraction() -> None:
    """Prior Tue session H=120 / L=80 -> PDH=120, PDL=80 on Wed."""
    tue = date(2025, 6, 3)
    wed = date(2025, 6, 4)
    bars = _session(tue, hi=120.0, lo=80.0) + _session(wed, hi=130.0, lo=90.0)
    src = PDHPDLSource(target_date=wed)
    ls = src.compute_levels("TEST", _history(bars))

    assert ls.symbol == "TEST"
    assert ls.session_date == wed
    kinds = sorted(lvl.kind for lvl in ls.levels)
    assert kinds == ["PDH", "PDL"]

    pdh = next(lvl for lvl in ls.levels if lvl.kind == "PDH")
    pdl = next(lvl for lvl in ls.levels if lvl.kind == "PDL")
    assert pdh.price == 120.0
    assert pdl.price == 80.0
    # Metadata records the prior session date.
    assert pdh.metadata["prior_date"] == tue.isoformat()
    assert pdh.metadata["rth_bar_count"] == 4


def test_target_date_inferred_from_history_when_not_set() -> None:
    """If target_date is omitted, the source uses the most-recent bar date."""
    tue = date(2025, 6, 3)
    wed = date(2025, 6, 4)
    bars = _session(tue, hi=120.0, lo=80.0) + _session(wed)
    src = PDHPDLSource()  # target_date=None -> infer from history
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.session_date == wed
    assert {lvl.kind for lvl in ls.levels} == {"PDH", "PDL"}


# ---------------------------------------------------------------------------
# Empty / degenerate inputs
# ---------------------------------------------------------------------------


def test_empty_history_returns_empty_level_set() -> None:
    src = PDHPDLSource(target_date=date(2025, 6, 4))
    ls = src.compute_levels("TEST", BarHistory(symbol="TEST", bars=[]))
    assert ls.levels == tuple()
    assert ls.session_date == date(2025, 6, 4)


def test_history_without_prior_session_returns_empty() -> None:
    """If only the target session is in history, there's no PDH/PDL to emit."""
    wed = date(2025, 6, 4)
    bars = _session(wed)
    src = PDHPDLSource(target_date=wed)
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()


def test_only_eh_bars_in_prior_session_returns_empty() -> None:
    """If the prior 'session' has only premarket / afterhours bars, no PDH/PDL."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    # Premarket and aftermarket only on Mon.
    bars = [
        _bar(mon, time(8, 0), o=100, h=120, lo=99, c=119),
        _bar(mon, time(16, 30), o=119, h=121, lo=118, c=120),
    ] + _session(tue, hi=130, lo=90)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()


# ---------------------------------------------------------------------------
# Multiple prior sessions
# ---------------------------------------------------------------------------


def test_most_recent_prior_session_wins() -> None:
    """If history has multiple prior sessions, the IMMEDIATELY prior one wins."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    wed = date(2025, 6, 4)
    bars = (
        _session(mon, hi=200.0, lo=50.0)   # noisy, far away
        + _session(tue, hi=120.0, lo=80.0)  # the one we want
        + _session(wed, hi=125.0, lo=95.0)
    )
    src = PDHPDLSource(target_date=wed)
    ls = src.compute_levels("TEST", _history(bars))
    pdh = next(lvl for lvl in ls.levels if lvl.kind == "PDH")
    pdl = next(lvl for lvl in ls.levels if lvl.kind == "PDL")
    # Tue wins, not Mon.
    assert pdh.price == 120.0
    assert pdl.price == 80.0
    assert pdh.metadata["prior_date"] == tue.isoformat()


# ---------------------------------------------------------------------------
# RTH boundary handling
# ---------------------------------------------------------------------------


def test_extended_hours_bars_excluded_from_pdh_pdl() -> None:
    """PM (>120) and AH (<70) prints in the prior session must not bleed in."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = [
        # Premarket spike — must be excluded.
        _bar(mon, time(8, 0), o=100, h=200.0, lo=99, c=150),
        # RTH session: real high = 120, real low = 80.
        *_session(mon, hi=120.0, lo=80.0),
        # Afterhours flush — must be excluded.
        _bar(mon, time(17, 0), o=85, h=85, lo=50.0, c=70),
    ] + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    pdh = next(lvl for lvl in ls.levels if lvl.kind == "PDH")
    pdl = next(lvl for lvl in ls.levels if lvl.kind == "PDL")
    assert pdh.price == 120.0  # not 200
    assert pdl.price == 80.0   # not 50


def test_rth_open_inclusive_close_exclusive() -> None:
    """09:30 counts as RTH; 16:00 does not."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = [
        _bar(mon, time(9, 30), o=100, h=125.0, lo=99, c=120),     # included
        _bar(mon, time(10, 0), o=120, h=121, lo=80.0, c=85),       # included (sets PDL=80)
        _bar(mon, time(16, 0), o=85, h=999.0, lo=10.0, c=50),     # EXCLUDED (16:00 exactly)
    ] + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    pdh = next(lvl for lvl in ls.levels if lvl.kind == "PDH")
    pdl = next(lvl for lvl in ls.levels if lvl.kind == "PDL")
    assert pdh.price == 125.0
    assert pdl.price == 80.0


# ---------------------------------------------------------------------------
# Staleness — Monday / post-holiday gap handling
# ---------------------------------------------------------------------------


def test_monday_after_friday_is_NOT_stale_default_gap() -> None:
    """Fri->Mon is 3 calendar days. Default max_gap_days=2 -> stale, returns empty.

    This is the documented Monday/holiday-skip behavior from the directive note.
    """
    fri = date(2025, 6, 6)   # Friday
    mon = date(2025, 6, 9)   # Monday — 3 calendar days later
    assert (mon - fri).days == 3
    bars = _session(fri, hi=120.0, lo=80.0) + _session(mon)
    src = PDHPDLSource(target_date=mon)  # default max_gap_days=2
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()


def test_monday_with_relaxed_gap_emits_levels() -> None:
    """If max_gap_days raised to 3, Mon-after-Fri does emit PDH/PDL."""
    fri = date(2025, 6, 6)
    mon = date(2025, 6, 9)
    bars = _session(fri, hi=120.0, lo=80.0) + _session(mon)
    src = PDHPDLSource(target_date=mon, max_gap_days=3)
    ls = src.compute_levels("TEST", _history(bars))
    assert {lvl.kind for lvl in ls.levels} == {"PDH", "PDL"}


def test_post_holiday_gap_returns_empty() -> None:
    """Markets closed Mon (e.g. MLK). Tue's prior session is Fri (4 days back)."""
    fri = date(2024, 1, 12)
    tue = date(2024, 1, 16)   # MLK is Mon 1/15 -> Tue 1/16
    assert (tue - fri).days == 4
    bars = _session(fri, hi=120.0, lo=80.0) + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()


def test_tuesday_after_normal_monday_is_not_stale() -> None:
    """Normal Mon -> Tue is 1 day. Always emits PDH/PDL."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = _session(mon, hi=120.0, lo=80.0) + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    assert {lvl.kind for lvl in ls.levels} == {"PDH", "PDL"}


# ---------------------------------------------------------------------------
# Pathological data
# ---------------------------------------------------------------------------


def test_pdh_less_than_pdl_refuses_to_emit() -> None:
    """A defensive guard — if data is corrupt and high < low, return empty."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    # Bar with high < low (data corruption).
    bars = [
        _bar(mon, time(11, 0), o=100, h=50, lo=200, c=100),  # corrupt
    ] + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()


def test_zero_or_negative_prices_refused() -> None:
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = [
        _bar(mon, time(11, 0), o=0, h=0, lo=0, c=0),
    ] + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()


# ---------------------------------------------------------------------------
# Intraday update is a no-op
# ---------------------------------------------------------------------------


def test_update_intraday_is_noop() -> None:
    """Pushing an intraday bar must not change the LevelSet — PDH/PDL is fixed."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = _session(mon, hi=120.0, lo=80.0) + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls_before = src.compute_levels("TEST", _history(bars))
    # Intraday bar with extreme high — must NOT raise PDH.
    src.update_intraday(_bar(tue, time(12, 0), o=120, h=999.0, lo=119, c=900))
    ls_after = src.compute_levels("TEST", _history(bars))
    assert ls_before.levels == ls_after.levels


# ---------------------------------------------------------------------------
# Per-bar arrival detection — integration with ArrivalDetector edge cases
# ---------------------------------------------------------------------------


def test_arrival_at_pdh_within_proximity_pct() -> None:
    """A bar at 0.05% below PDH fires arrival at the PDH (within 0.1% window)."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = _session(mon, hi=120.0, lo=80.0)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    det = ArrivalDetector(proximity_pct=0.001)  # 0.1%

    # At $119.95 (0.04% below 120), arrival fires at PDH.
    arrived = det.check_arrival("TEST", 119.95, ls)
    assert arrived is not None
    assert arrived.kind == "PDH"
    assert arrived.price == 120.0


def test_arrival_at_pdh_just_outside_proximity_returns_none() -> None:
    """A bar at 0.2% below PDH does NOT fire arrival (outside 0.1% window)."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = _session(mon, hi=120.0, lo=80.0)
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    det = ArrivalDetector(proximity_pct=0.001)  # 0.1%
    # $119.50 is ~0.42% below 120 — outside the 0.1% window.
    # PDL is at 80 (more than 49% away). Neither in range.
    assert det.check_arrival("TEST", 119.50, ls) is None


def test_arrival_chooses_first_level_in_set_when_both_in_range() -> None:
    """When PDH and PDL are both within proximity (unrealistic but defensible),
    first-in-level-set wins (PDH precedes PDL by construction)."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    # Tight prior session: H=100.10, L=99.90 — both within 0.1% of 100.
    bars = [
        _bar(mon, time(9, 30), o=100, h=100.05, lo=99.95, c=100.0),
        _bar(mon, time(11, 0), o=100.0, h=100.10, lo=99.90, c=100.0),
    ]
    src = PDHPDLSource(target_date=tue)
    ls = src.compute_levels("TEST", _history(bars))
    pdh = next(lvl for lvl in ls.levels if lvl.kind == "PDH")
    pdl = next(lvl for lvl in ls.levels if lvl.kind == "PDL")
    assert pdh.price == 100.10
    assert pdl.price == 99.90
    # Big proximity to deliberately catch both (0.5% of 100 = $0.50).
    det = ArrivalDetector(proximity_pct=0.005)
    arrived = det.check_arrival("TEST", 100.0, ls)
    assert arrived is not None
    # PDH precedes PDL in the LevelSet by construction.
    assert arrived.kind == "PDH"
    assert arrived.price == 100.10


def test_arrival_returns_none_when_level_set_empty_due_to_staleness() -> None:
    """If staleness gate empties the LevelSet, arrival cannot fire."""
    fri = date(2025, 6, 6)
    mon = date(2025, 6, 9)   # 3 calendar days -> stale at default max_gap_days=2
    bars = _session(fri, hi=120.0, lo=80.0)
    src = PDHPDLSource(target_date=mon)
    ls = src.compute_levels("TEST", _history(bars))
    assert ls.levels == tuple()
    det = ArrivalDetector(proximity_pct=0.01)
    assert det.check_arrival("TEST", 120.0, ls) is None


# ---------------------------------------------------------------------------
# Determinism / idempotency
# ---------------------------------------------------------------------------


def test_compute_levels_is_idempotent() -> None:
    """Calling compute_levels twice on the same history yields equal LevelSets."""
    mon = date(2025, 6, 2)
    tue = date(2025, 6, 3)
    bars = _session(mon, hi=120.0, lo=80.0) + _session(tue)
    src = PDHPDLSource(target_date=tue)
    ls1 = src.compute_levels("TEST", _history(bars))
    ls2 = src.compute_levels("TEST", _history(bars))
    assert ls1.levels == ls2.levels
    assert ls1.session_date == ls2.session_date
