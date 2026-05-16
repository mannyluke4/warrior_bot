"""PDHPDLSource — prior session's RTH high and low.

The PDH/PDL level source pulls the prior RTH session (09:30-16:00 ET) high
and low and emits them as the LevelSet for the current session. These are
canonical "stop-hunt" and "magnet" levels in equities — institutional desks
key off them for fade and breakout plays alike.

Design (per DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3 Agent H and
DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §4.3):

- `compute_levels(symbol, history)` — scans the most recent prior RTH session
  in `history`, returns LevelSet with one `Level(kind='PDH')` and one
  `Level(kind='PDL')`.
- `update_intraday(bar)` — no-op. PDH/PDL is fixed at session start; it does
  not evolve with intraday price.

Staleness gate — Monday / post-holiday handling:

If the prior session is more than `max_gap_days` calendar days behind the
target session (default 2), the source returns an empty `LevelSet`. This
reflects the empirical reality that a Friday close from 4+ days ago is a
stale magnet — overnight news cycles dilute the level's relevance and the
practitioner literature (and the directive note for this agent) calls out
post-long-weekend / post-holiday PDH/PDL as low-edge.

Edge cases handled:
- Empty history -> empty LevelSet
- History contains only the target session (no prior session) -> empty LevelSet
- History bars outside RTH only -> empty LevelSet (no RTH session to read)
- Multiple prior sessions present -> the IMMEDIATELY prior RTH session wins
  (largest session_date < target_date)
- Bars with timestamps but no time-of-day info: defensively coerce via
  `datetime.time()` — any bar whose timestamp falls inside 09:30:00-15:59:59
  ET counts as RTH. Bars must be timezone-naive ET to match the framework
  convention (see level_sources/base.py docstring).

Behavior is deterministic and pure: no I/O, no clock reads, no globals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
    LevelSourceProtocol,
)


# RTH boundaries (ET, naive).
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)


def _in_rth(ts: datetime) -> bool:
    """True if `ts.time()` is inside [09:30, 16:00)."""
    t = ts.time()
    return _RTH_OPEN <= t < _RTH_CLOSE


@dataclass
class PDHPDLSource:
    """Level source emitting prior-session RTH high (PDH) and low (PDL).

    Args:
        target_date: The session whose levels to compute (i.e. the current
            trading day). If None, defaults to the most recent date in the
            history; tests typically pass this explicitly. Strategy
            orchestrators pass the session being traded.
        max_gap_days: Maximum calendar-day gap between the prior session
            and `target_date` before the level set is considered stale.
            Default 2: Friday->Monday is 3 calendar days; the gate skips
            the level set on Monday or post-holiday Tuesday by default.

    The dataclass intentionally does not freeze: `update_intraday` is
    mutating-by-contract (no-op here but plugin lifecycle expects mutability).
    """

    target_date: Optional[date] = None
    max_gap_days: int = 2

    # No internal mutable state needed — PDH/PDL is fixed at session start.
    # We keep a slot for the last LevelSet so callers can `re-read` without
    # recomputing.
    _last_level_set: Optional[LevelSet] = field(default=None, init=False, repr=False)

    # -- LevelSourceProtocol ----------------------------------------------------

    def compute_levels(self, symbol: str, history: BarHistory) -> LevelSet:
        """Scan `history`, return LevelSet of prior RTH H/L for `target_date`.

        Returns an empty LevelSet if the prior session is missing or stale.
        """
        target = self._resolve_target_date(history)
        if target is None:
            return self._empty(symbol, date.today())

        prior_date = self._prior_session_date(history, target)
        if prior_date is None:
            return self._empty(symbol, target)

        # Staleness gate: prior session must be within max_gap_days of target.
        gap = (target - prior_date).days
        if gap > self.max_gap_days:
            ls = self._empty(symbol, target)
            self._last_level_set = ls
            return ls

        prior_rth_bars = [
            b for b in history.bars
            if b.timestamp.date() == prior_date and _in_rth(b.timestamp)
        ]
        if not prior_rth_bars:
            ls = self._empty(symbol, target)
            self._last_level_set = ls
            return ls

        pdh = max(b.high for b in prior_rth_bars)
        pdl = min(b.low for b in prior_rth_bars)
        if pdh <= 0 or pdl <= 0 or pdh < pdl:
            # Pathological — refuse to emit.
            ls = self._empty(symbol, target)
            self._last_level_set = ls
            return ls

        levels = (
            Level(
                price=pdh,
                kind="PDH",
                session_date=target,
                metadata={
                    "prior_date": prior_date.isoformat(),
                    "rth_bar_count": len(prior_rth_bars),
                },
            ),
            Level(
                price=pdl,
                kind="PDL",
                session_date=target,
                metadata={
                    "prior_date": prior_date.isoformat(),
                    "rth_bar_count": len(prior_rth_bars),
                },
            ),
        )
        ls = LevelSet(symbol=symbol, session_date=target, levels=levels)
        self._last_level_set = ls
        return ls

    def update_intraday(self, bar: Bar) -> None:
        """No-op. PDH/PDL are session-start fixtures; intraday bars don't move them."""
        return None

    # -- helpers ----------------------------------------------------------------

    def _resolve_target_date(self, history: BarHistory) -> Optional[date]:
        if self.target_date is not None:
            return self.target_date
        if len(history) == 0:
            return None
        return max(b.timestamp.date() for b in history.bars)

    def _prior_session_date(
        self, history: BarHistory, target: date
    ) -> Optional[date]:
        """Largest session_date in history strictly less than `target`."""
        prior_dates = {
            b.timestamp.date() for b in history.bars
            if b.timestamp.date() < target and _in_rth(b.timestamp)
        }
        if not prior_dates:
            return None
        return max(prior_dates)

    def _empty(self, symbol: str, session_date: date) -> LevelSet:
        return LevelSet(symbol=symbol, session_date=session_date, levels=tuple())


# Convenience for orchestrators that want a singleton across sessions —
# they can re-bind .target_date per session rather than re-instantiate.
__all__ = ["PDHPDLSource"]
