"""Anchored VWAP level source — Wave 5, Agent M (renamed from directive's
Agent O slot; CC's Wave 5 assignment per ``DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md``
§5 / DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §4.6 / §5.2).

The Anchored VWAP (AVWAP) is the volume-weighted average price computed *from
a chosen anchor event forward* (rather than from session-open like the normal
session VWAP). Anchors are typically high-information events:

- **gap_day**: open of the most recent session where ``open / prior_close``
  diverged by more than a configured threshold (default 2%). Gap-day AVWAPs
  capture the "where institutions have been net-buying / net-selling since
  the gap" — a key support/resistance reference for swing traders.
- **earnings**: open of the most recent earnings reaction day. For symbols
  with cached earnings dates, we anchor to the first session after the
  earnings release. Earnings AVWAP often acts as a hard institutional
  support/resistance for the following weeks.
- **fomc**: open of FOMC announcement days (8 per year). For index-correlated
  tickers, the FOMC AVWAP is a meaningful regime reference.
- **multi_anchor**: emit AVWAPs from each of the most recent anchors
  simultaneously (up to ``multi_anchor_count``, default 3). Strategies can
  then look for confluence across multiple anchors.

Math (volume-weighted average from anchor index forward):

    typical_i = (high_i + low_i + close_i) / 3
    cum_pv    = sum_{j >= anchor_idx} typical_j * volume_j
    cum_vol   = sum_{j >= anchor_idx} volume_j
    avwap     = cum_pv / cum_vol

Where ``anchor_idx`` is the index of the first bar at-or-after the anchor
timestamp. The math is identical to ``VWAPSource`` except cumulative sums
start at the anchor instead of session-open.

Anchor identification operates on **daily bar history** (or, equivalently,
the first RTH bar of each session). For backtesting we rely on the strategy
runner to pass us a multi-session ``BarHistory``; we then walk back through
session boundaries to identify candidates.

This module is **research / backtest infrastructure** — it does not touch
the existing live stack. See DIRECTIVE §7 and CLAUDE.md "Critical Rules".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Literal, Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
)


# RTH boundaries (ET, naive — same convention as the rest of the framework).
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)


AnchorType = Literal[
    "gap_day", "earnings", "fomc", "earnings_or_gap", "multi_anchor"
]


# ---------------------------------------------------------------------------
# Hardcoded FOMC announcement calendar (2018-2024) — 8 per year.
# These are the FOMC statement dates (~2pm ET press release / projections).
# Source: federalreserve.gov FOMC meeting calendars.
# ---------------------------------------------------------------------------
FOMC_DATES: tuple[date, ...] = (
    date(2018, 1, 31), date(2018, 3, 21), date(2018, 5, 2),  date(2018, 6, 13),
    date(2018, 8, 1),  date(2018, 9, 26), date(2018, 11, 8), date(2018, 12, 19),
    date(2019, 1, 30), date(2019, 3, 20), date(2019, 5, 1),  date(2019, 6, 19),
    date(2019, 7, 31), date(2019, 9, 18), date(2019, 10, 30), date(2019, 12, 11),
    date(2020, 1, 29), date(2020, 3, 3),  date(2020, 3, 15), date(2020, 3, 23),
    date(2020, 4, 29), date(2020, 6, 10), date(2020, 7, 29), date(2020, 9, 16),
    date(2020, 11, 5), date(2020, 12, 16),
    date(2021, 1, 27), date(2021, 3, 17), date(2021, 4, 28), date(2021, 6, 16),
    date(2021, 7, 28), date(2021, 9, 22), date(2021, 11, 3), date(2021, 12, 15),
    date(2022, 1, 26), date(2022, 3, 16), date(2022, 5, 4),  date(2022, 6, 15),
    date(2022, 7, 27), date(2022, 9, 21), date(2022, 11, 2), date(2022, 12, 14),
    date(2023, 2, 1),  date(2023, 3, 22), date(2023, 5, 3),  date(2023, 6, 14),
    date(2023, 7, 26), date(2023, 9, 20), date(2023, 11, 1), date(2023, 12, 13),
    date(2024, 1, 31), date(2024, 3, 20), date(2024, 5, 1),  date(2024, 6, 12),
    date(2024, 7, 31), date(2024, 9, 18), date(2024, 11, 7), date(2024, 12, 18),
)


# ---------------------------------------------------------------------------
# Stub earnings calendar (Databento Standard doesn't include corporate-action
# event data on the equity tier; we hardcode AAPL/MSFT/NVDA/META/AMD/GOOGL
# earnings dates 2020-2024 from public investor-relations releases). Per
# directive: "use a stub list for now if Databento doesn't have it".
#
# Dates are the *announcement* dates (post-close earnings releases). The
# earnings anchor for AVWAP is the OPEN of the FIRST RTH SESSION AFTER the
# release — which is captured below by storing the next-session date.
# ---------------------------------------------------------------------------
EARNINGS_CALENDAR: dict[str, tuple[date, ...]] = {
    "AAPL": (
        date(2020, 1, 29), date(2020, 4, 30), date(2020, 7, 30), date(2020, 10, 29),
        date(2021, 1, 28), date(2021, 4, 28), date(2021, 7, 27), date(2021, 10, 28),
        date(2022, 1, 27), date(2022, 4, 28), date(2022, 7, 28), date(2022, 10, 27),
        date(2023, 2, 2),  date(2023, 5, 4),  date(2023, 8, 3),  date(2023, 11, 2),
        date(2024, 2, 1),  date(2024, 5, 2),  date(2024, 8, 1),  date(2024, 10, 31),
    ),
    "MSFT": (
        date(2020, 1, 29), date(2020, 4, 29), date(2020, 7, 22), date(2020, 10, 27),
        date(2021, 1, 26), date(2021, 4, 27), date(2021, 7, 27), date(2021, 10, 26),
        date(2022, 1, 25), date(2022, 4, 26), date(2022, 7, 26), date(2022, 10, 25),
        date(2023, 1, 24), date(2023, 4, 25), date(2023, 7, 25), date(2023, 10, 24),
        date(2024, 1, 30), date(2024, 4, 25), date(2024, 7, 30), date(2024, 10, 30),
    ),
    "NVDA": (
        date(2020, 2, 13), date(2020, 5, 21), date(2020, 8, 19), date(2020, 11, 18),
        date(2021, 2, 24), date(2021, 5, 26), date(2021, 8, 18), date(2021, 11, 17),
        date(2022, 2, 16), date(2022, 5, 25), date(2022, 8, 24), date(2022, 11, 16),
        date(2023, 2, 22), date(2023, 5, 24), date(2023, 8, 23), date(2023, 11, 21),
        date(2024, 2, 21), date(2024, 5, 22), date(2024, 8, 28), date(2024, 11, 20),
    ),
    "META": (
        date(2020, 1, 29), date(2020, 4, 29), date(2020, 7, 30), date(2020, 10, 29),
        date(2021, 1, 27), date(2021, 4, 28), date(2021, 7, 28), date(2021, 10, 25),
        date(2022, 2, 2),  date(2022, 4, 27), date(2022, 7, 27), date(2022, 10, 26),
        date(2023, 2, 1),  date(2023, 4, 26), date(2023, 7, 26), date(2023, 10, 25),
        date(2024, 2, 1),  date(2024, 4, 24), date(2024, 7, 31), date(2024, 10, 30),
    ),
    "AMD": (
        date(2020, 1, 28), date(2020, 4, 28), date(2020, 7, 28), date(2020, 10, 27),
        date(2021, 1, 26), date(2021, 4, 27), date(2021, 7, 27), date(2021, 10, 26),
        date(2022, 2, 1),  date(2022, 5, 3),  date(2022, 8, 2),  date(2022, 11, 1),
        date(2023, 1, 31), date(2023, 5, 2),  date(2023, 8, 1),  date(2023, 10, 31),
        date(2024, 1, 30), date(2024, 4, 30), date(2024, 7, 30), date(2024, 10, 29),
    ),
    "TSLA": (
        date(2020, 1, 29), date(2020, 4, 29), date(2020, 7, 22), date(2020, 10, 21),
        date(2021, 1, 27), date(2021, 4, 26), date(2021, 7, 26), date(2021, 10, 20),
        date(2022, 1, 26), date(2022, 4, 20), date(2022, 7, 20), date(2022, 10, 19),
        date(2023, 1, 25), date(2023, 4, 19), date(2023, 7, 19), date(2023, 10, 18),
        date(2024, 1, 24), date(2024, 4, 23), date(2024, 7, 23), date(2024, 10, 23),
    ),
    "GOOGL": (
        date(2020, 2, 3),  date(2020, 4, 28), date(2020, 7, 30), date(2020, 10, 29),
        date(2021, 2, 2),  date(2021, 4, 27), date(2021, 7, 27), date(2021, 10, 26),
        date(2022, 2, 1),  date(2022, 4, 26), date(2022, 7, 26), date(2022, 10, 25),
        date(2023, 2, 2),  date(2023, 4, 25), date(2023, 7, 25), date(2023, 10, 24),
        date(2024, 1, 30), date(2024, 4, 25), date(2024, 7, 23), date(2024, 10, 29),
    ),
}


# ---------------------------------------------------------------------------
# Anchor identification helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """One anchor candidate.

    ``date``: session date of the anchor bar.
    ``anchor_ts``: timestamp of the first bar at-or-after the anchor moment
        (typically 09:30 ET of the anchor session).
    ``kind``: 'gap_day' | 'earnings' | 'fomc'.
    ``metadata``: source-specific info (e.g. gap_pct for gap_day).
    """

    session_date: date
    anchor_ts: datetime
    kind: str
    metadata: dict


def _in_rth(ts: datetime) -> bool:
    t = ts.time()
    return _RTH_OPEN <= t < _RTH_CLOSE


def _first_rth_bar_index_for_date(
    bars: list[Bar], target_date: date
) -> Optional[int]:
    """Index of the first RTH bar in `bars` whose date == target_date.

    Returns None if no such bar exists.
    """
    for i, b in enumerate(bars):
        if b.timestamp.date() == target_date and _in_rth(b.timestamp):
            return i
    return None


def _session_dates(bars: list[Bar]) -> list[date]:
    """Sorted unique session dates with at least one RTH bar."""
    seen: set[date] = set()
    out: list[date] = []
    for b in bars:
        if _in_rth(b.timestamp):
            d = b.timestamp.date()
            if d not in seen:
                seen.add(d)
                out.append(d)
    return sorted(out)


def _session_first_rth_bar(
    bars: list[Bar], session_date: date
) -> Optional[Bar]:
    """First (earliest) RTH bar for a session."""
    earliest: Optional[Bar] = None
    for b in bars:
        if b.timestamp.date() != session_date or not _in_rth(b.timestamp):
            continue
        if earliest is None or b.timestamp < earliest.timestamp:
            earliest = b
    return earliest


def _session_last_rth_close(
    bars: list[Bar], session_date: date
) -> Optional[float]:
    """Last (latest) RTH bar close for a session — used as prior-close proxy."""
    latest: Optional[Bar] = None
    for b in bars:
        if b.timestamp.date() != session_date or not _in_rth(b.timestamp):
            continue
        if latest is None or b.timestamp > latest.timestamp:
            latest = b
    return latest.close if latest else None


def detect_gap_days(
    bars: list[Bar],
    *,
    target_date: date,
    lookback_days: int,
    gap_threshold_pct: float = 0.02,
) -> list[Anchor]:
    """Find sessions whose open diverged from the prior session's close by
    at least ``gap_threshold_pct`` (default 2%) within the lookback window.

    Returns anchors sorted by session date DESCENDING (most-recent first).
    """
    sessions = _session_dates(bars)
    # Filter to lookback window strictly before target_date.
    earliest_allowed = target_date - timedelta(days=lookback_days)
    candidates = [d for d in sessions if earliest_allowed <= d < target_date]
    out: list[Anchor] = []
    for s in candidates:
        # Need a prior session to compute gap. Find the immediately-prior
        # session date.
        prior_idx = sessions.index(s) - 1
        if prior_idx < 0:
            continue
        prior_date = sessions[prior_idx]
        prior_close = _session_last_rth_close(bars, prior_date)
        first_bar = _session_first_rth_bar(bars, s)
        if first_bar is None or prior_close is None or prior_close <= 0:
            continue
        gap_pct = (first_bar.open - prior_close) / prior_close
        if abs(gap_pct) >= gap_threshold_pct:
            out.append(Anchor(
                session_date=s,
                anchor_ts=first_bar.timestamp,
                kind="gap_day",
                metadata={
                    "gap_pct": gap_pct,
                    "prior_close": prior_close,
                    "open": first_bar.open,
                },
            ))
    # Newest first
    out.sort(key=lambda a: a.session_date, reverse=True)
    return out


def detect_earnings_anchors(
    bars: list[Bar],
    *,
    symbol: str,
    target_date: date,
    lookback_days: int,
) -> list[Anchor]:
    """Find recent earnings reaction days for ``symbol``.

    The "reaction day" is the first RTH session AFTER the earnings release.
    Most companies in our stub list release post-close, so the reaction day
    is typically the next trading day.

    Returns anchors sorted by session date DESCENDING.
    """
    if symbol not in EARNINGS_CALENDAR:
        return []
    earliest_allowed = target_date - timedelta(days=lookback_days)
    sessions_present = _session_dates(bars)
    if not sessions_present:
        return []
    sessions_present_set = set(sessions_present)

    out: list[Anchor] = []
    for release in EARNINGS_CALENDAR[symbol]:
        if release < earliest_allowed or release >= target_date:
            continue
        # Find the first RTH session AT-OR-AFTER the release day.
        # Most releases are post-close, so reaction = release_date if there's
        # a session that day with bars (i.e. the release happened post-close
        # OF that date — bars on release_date are pre-release-content for
        # us... but for an AVWAP from "earnings open" the standard convention
        # is to anchor at the OPEN of the *next* RTH session after release.
        # Find next session strictly after release_date.
        reaction_date = None
        for s in sessions_present:
            if s > release:
                reaction_date = s
                break
        if reaction_date is None or reaction_date not in sessions_present_set:
            continue
        first_bar = _session_first_rth_bar(bars, reaction_date)
        if first_bar is None:
            continue
        out.append(Anchor(
            session_date=reaction_date,
            anchor_ts=first_bar.timestamp,
            kind="earnings",
            metadata={"release_date": release.isoformat()},
        ))
    out.sort(key=lambda a: a.session_date, reverse=True)
    return out


def detect_fomc_anchors(
    bars: list[Bar],
    *,
    target_date: date,
    lookback_days: int,
) -> list[Anchor]:
    """Find recent FOMC announcement sessions within the lookback window.

    FOMC anchors use the OPEN of the FOMC day itself (the regime change
    happens at 2pm ET on FOMC day; the AVWAP from the open captures the
    whole day's reaction).

    Returns anchors sorted by session date DESCENDING.
    """
    earliest_allowed = target_date - timedelta(days=lookback_days)
    sessions_present_set = set(_session_dates(bars))
    out: list[Anchor] = []
    for fomc_date in FOMC_DATES:
        if fomc_date < earliest_allowed or fomc_date >= target_date:
            continue
        if fomc_date not in sessions_present_set:
            continue
        first_bar = _session_first_rth_bar(bars, fomc_date)
        if first_bar is None:
            continue
        out.append(Anchor(
            session_date=fomc_date,
            anchor_ts=first_bar.timestamp,
            kind="fomc",
            metadata={},
        ))
    out.sort(key=lambda a: a.session_date, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Per-anchor running VWAP accumulator
# ---------------------------------------------------------------------------


@dataclass
class _AVWAPState:
    """O(1) running VWAP accumulator for one anchor."""

    anchor_ts: datetime
    anchor_kind: str
    anchor_metadata: dict
    cum_pv: float = 0.0
    cum_vol: float = 0.0
    n_bars: int = 0

    @staticmethod
    def _typical(bar: Bar) -> float:
        return (bar.high + bar.low + bar.close) / 3.0

    def ingest(self, bar: Bar) -> None:
        """Add one bar to the running average (skips bars before anchor or
        with non-positive / non-finite volume)."""
        if bar.timestamp < self.anchor_ts:
            return
        v = bar.volume
        if v is None:
            return
        try:
            vv = float(v)
        except (TypeError, ValueError):
            return
        if not math.isfinite(vv) or vv <= 0:
            return
        tp = self._typical(bar)
        if not math.isfinite(tp):
            return
        self.cum_pv += tp * vv
        self.cum_vol += vv
        self.n_bars += 1

    @property
    def avwap(self) -> Optional[float]:
        if self.cum_vol <= 0:
            return None
        return self.cum_pv / self.cum_vol


# ---------------------------------------------------------------------------
# Public source — implements LevelSourceProtocol
# ---------------------------------------------------------------------------


@dataclass
class AnchoredVWAPSource:
    """AVWAP level source.

    Configuration:
        anchor_type: 'gap_day' | 'earnings' | 'fomc' | 'earnings_or_gap' |
                     'multi_anchor'
        lookback_days: How far back to scan for anchor candidates (sessions).
            Default 30.
        multi_anchor_count: For 'multi_anchor', how many anchors to track
            (most-recent N across the union of gap+earnings+fomc). Default 3.
        gap_threshold_pct: For gap_day detection, minimum |gap| fraction.
            Default 0.02 (2%).

    Lifecycle:
        - ``compute_levels(symbol, history)`` scans `history` for anchors,
          spins up one ``_AVWAPState`` per chosen anchor, and replays all
          bars from each anchor up to the target session.
        - ``update_intraday(bar)`` appends a new bar to every active anchor's
          running average. Returns the LevelSet next time ``current_levelset``
          is read.
        - ``current_levelset()`` returns the current AVWAP price for each
          anchor as a separate ``Level(kind='AVWAP')`` with metadata
          identifying the anchor type and date.

    The target session is inferred from the most-recent bar in history at
    ``compute_levels`` time, OR may be passed explicitly via the
    ``target_date`` argument (preferred from runners). Anchors are required
    to be strictly before the target session.
    """

    anchor_type: AnchorType = "gap_day"
    lookback_days: int = 30
    multi_anchor_count: int = 3
    gap_threshold_pct: float = 0.02

    # Internal: one accumulator per active anchor.
    _states: list[_AVWAPState] = field(default_factory=list, init=False, repr=False)
    _target_date: Optional[date] = field(default=None, init=False, repr=False)
    _symbol: str = field(default="", init=False, repr=False)

    # ── public API ──────────────────────────────────────────────────────

    def compute_levels(
        self,
        symbol: str,
        history: BarHistory,
        target_date: Optional[date] = None,
    ) -> LevelSet:
        """Identify anchors in ``history``, build the initial AVWAP set.

        Replays bars from each anchor through the end of ``history`` so the
        returned LevelSet reflects state at the most-recent bar.
        """
        self._symbol = symbol or history.symbol
        if target_date is None:
            target_date = self._infer_target_date(history)
        if target_date is None:
            # Empty / unusable history — return empty levelset.
            self._target_date = date.today()
            self._states = []
            return LevelSet(symbol=self._symbol, session_date=date.today(), levels=tuple())
        self._target_date = target_date

        anchors = self._select_anchors(history, target_date)
        self._states = [
            _AVWAPState(
                anchor_ts=a.anchor_ts,
                anchor_kind=a.kind,
                anchor_metadata={"anchor_date": a.session_date.isoformat(), **a.metadata},
            )
            for a in anchors
        ]
        # Replay all bars at-or-after the earliest anchor up to end-of-history.
        if self._states:
            earliest_anchor_ts = min(s.anchor_ts for s in self._states)
            for bar in history.bars:
                if bar.timestamp < earliest_anchor_ts:
                    continue
                # We stop ingesting at the start of the target session; the
                # caller invokes `update_intraday` for intraday bars.
                # For backtest convenience, ingest *all* bars (intraday too)
                # if the caller hands us a fully-populated history.
                for s in self._states:
                    s.ingest(bar)
        return self._build_levelset()

    def update_intraday(self, bar: Bar) -> None:
        """Append one bar to every active anchor's running average."""
        if not self._states:
            return
        for s in self._states:
            s.ingest(bar)

    def current_levelset(self, symbol: Optional[str] = None) -> LevelSet:
        """Return the latest LevelSet without recomputing anchors."""
        if symbol:
            self._symbol = symbol
        return self._build_levelset()

    # ── anchor selection ────────────────────────────────────────────────

    def _select_anchors(
        self, history: BarHistory, target_date: date
    ) -> list[Anchor]:
        """Apply the configured anchor_type policy and return the chosen anchors."""
        sym = self._symbol or history.symbol
        if self.anchor_type == "gap_day":
            gaps = detect_gap_days(
                history.bars,
                target_date=target_date,
                lookback_days=self.lookback_days,
                gap_threshold_pct=self.gap_threshold_pct,
            )
            return gaps[:1]  # most-recent only
        if self.anchor_type == "earnings":
            earns = detect_earnings_anchors(
                history.bars,
                symbol=sym,
                target_date=target_date,
                lookback_days=self.lookback_days,
            )
            return earns[:1]
        if self.anchor_type == "fomc":
            fomc = detect_fomc_anchors(
                history.bars,
                target_date=target_date,
                lookback_days=self.lookback_days,
            )
            return fomc[:1]
        if self.anchor_type == "earnings_or_gap":
            earns = detect_earnings_anchors(
                history.bars,
                symbol=sym,
                target_date=target_date,
                lookback_days=self.lookback_days,
            )
            gaps = detect_gap_days(
                history.bars,
                target_date=target_date,
                lookback_days=self.lookback_days,
                gap_threshold_pct=self.gap_threshold_pct,
            )
            # Prefer earnings if recent; else gap.
            combined = sorted(
                earns + gaps,
                key=lambda a: a.session_date,
                reverse=True,
            )
            # Dedupe by session_date — first wins per date.
            seen: set[date] = set()
            out: list[Anchor] = []
            for a in combined:
                if a.session_date in seen:
                    continue
                seen.add(a.session_date)
                out.append(a)
                if len(out) >= self.multi_anchor_count:
                    break
            return out[:1] if self.anchor_type != "earnings_or_gap" else out
        # multi_anchor: union of all anchor types, most-recent N
        gaps = detect_gap_days(
            history.bars,
            target_date=target_date,
            lookback_days=self.lookback_days,
            gap_threshold_pct=self.gap_threshold_pct,
        )
        earns = detect_earnings_anchors(
            history.bars,
            symbol=sym,
            target_date=target_date,
            lookback_days=self.lookback_days,
        )
        fomc = detect_fomc_anchors(
            history.bars,
            target_date=target_date,
            lookback_days=self.lookback_days,
        )
        combined = sorted(
            gaps + earns + fomc,
            key=lambda a: a.session_date,
            reverse=True,
        )
        seen: set[date] = set()
        out: list[Anchor] = []
        for a in combined:
            if a.session_date in seen:
                continue
            seen.add(a.session_date)
            out.append(a)
            if len(out) >= self.multi_anchor_count:
                break
        return out

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _infer_target_date(history: BarHistory) -> Optional[date]:
        if not history.bars:
            return None
        return max(b.timestamp.date() for b in history.bars)

    def _build_levelset(self) -> LevelSet:
        sd = self._target_date or date.today()
        sym = self._symbol or ""
        if not self._states:
            return LevelSet(symbol=sym, session_date=sd, levels=tuple())
        levels: list[Level] = []
        for s in self._states:
            price = s.avwap
            if price is None or not math.isfinite(price):
                continue
            metadata = {
                "anchor_type": s.anchor_kind,
                "anchor_ts": s.anchor_ts.isoformat(),
                "n_bars": s.n_bars,
                **s.anchor_metadata,
            }
            levels.append(Level(
                price=price,
                kind="AVWAP",
                session_date=sd,
                metadata=metadata,
            ))
        return LevelSet(symbol=sym, session_date=sd, levels=tuple(levels))


__all__ = [
    "AnchoredVWAPSource",
    "Anchor",
    "FOMC_DATES",
    "EARNINGS_CALENDAR",
    "detect_gap_days",
    "detect_earnings_anchors",
    "detect_fomc_anchors",
]
