"""OpeningRangeSource — first-N-minute opening range high/low level source.

Implements `LevelSourceProtocol` for the ORB (Opening Range Breakout) strategy.

Design source:
- DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §4.1
- DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3 Agent F
- Zarattini et al. (2024) SSRN — 5-minute opening range is canonical

How it works
------------
1. `compute_levels(symbol, history)` walks the bar history for the session
   and identifies bars whose timestamps fall in the [09:30, 09:30+N) ET
   window. The high of those bars becomes ORH, the low becomes ORL.
2. `update_intraday(bar)` is a no-op: the opening range is fixed once the
   first N minutes have elapsed. Strategies should call `compute_levels`
   AFTER the first N RTH minutes have closed.

Bar timestamp convention
------------------------
The framework's Bar dataclass uses naïve datetimes. For Databento `ohlcv-1m`
the bar timestamp is the *open* of the minute, in UTC (e.g. 14:30 UTC =
09:30 ET during standard time, 13:30 UTC during DST). To remain agnostic
to tz, the implementation supports two strategies controlled by
`session_open_local`:

* **`session_open_local=True`** (default): timestamps are treated as
  already in market-local time (ET). The opening range is built from
  bars in [09:30, 09:30+N).

* **`session_open_local=False`**: timestamps are UTC, and the code looks
  for the first bar whose minute-of-day equals one of:
  - 14:30 (standard time, EST)
  - 13:30 (DST, EDT)
  Whichever appears first marks 09:30 ET. The opening range then spans
  the next N consecutive minutes.

Tests use synthetic bars with naïve ET timestamps, so the default
`session_open_local=True` is the canonical path.

5-min direction bias
--------------------
Per Zarattini's "Stocks in Play" filter, the direction of the opening 5m
bar (green = long bias, red = short bias) gates trade direction. We
expose this via the LevelSet metadata so the strategy layer can read it:

    level_set.levels[0].metadata.get("direction_bias")  # "long" | "short" | "neutral"

Reaching it via metadata keeps the LevelSet shape stable across strategies.

Author: Agent F (Wave 2 — Healthy Fluctuation Framework)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
    LevelSourceProtocol,
)


# Market open in ET. The opening range window is [09:30, 09:30 + minutes).
_MARKET_OPEN_ET = time(9, 30)

# UTC minute-of-day for 09:30 ET (standard / DST).
_OPEN_MINUTE_UTC_EST = 14 * 60 + 30   # 14:30 UTC = 09:30 EST
_OPEN_MINUTE_UTC_EDT = 13 * 60 + 30   # 13:30 UTC = 09:30 EDT


@dataclass(frozen=True)
class OpeningRangeSource:
    """Compute opening-range high/low from the first N RTH minutes.

    Parameters
    ----------
    minutes : int
        Length of the opening range in minutes. Default 5.
    use_5min_direction_bias : bool
        Attach a ``direction_bias`` metadata field to each emitted level
        based on the opening bar's color (close > open → "long",
        close < open → "short", flat → "neutral"). Default True.
    session_open_local : bool
        Whether to treat bar timestamps as already in market-local time
        (default True). If False, the source looks for 14:30 / 13:30 UTC
        as 09:30 ET (EST / EDT respectively).
    require_full_window : bool
        If True, return an empty LevelSet when fewer than `minutes` bars
        are present in the opening window. If False, build the OR from
        whatever bars are available (clip-to-end behavior). Default True.
    """

    minutes: int = 5
    use_5min_direction_bias: bool = True
    session_open_local: bool = True
    require_full_window: bool = True

    # ----- protocol methods -----------------------------------------------

    def compute_levels(self, symbol: str, history: BarHistory) -> LevelSet:
        if self.minutes <= 0:
            raise ValueError(f"minutes must be > 0, got {self.minutes}")
        if not history.bars:
            return LevelSet(symbol=symbol, session_date=date.today(), levels=())

        # Locate the opening window (first `minutes` bars starting at 09:30 ET).
        opening_bars = self._opening_bars(history.bars)
        if not opening_bars:
            return LevelSet(symbol=symbol, session_date=history.bars[0].timestamp.date(), levels=())

        if self.require_full_window and len(opening_bars) < self.minutes:
            # Not enough bars (e.g. half-day or partial data) — refuse to
            # emit a malformed range rather than fire a trade off a 1m sample.
            return LevelSet(
                symbol=symbol,
                session_date=opening_bars[0].timestamp.date(),
                levels=(),
            )

        orh = max(b.high for b in opening_bars)
        orl = min(b.low for b in opening_bars)
        session_date = opening_bars[0].timestamp.date()

        # Direction bias: from the FIRST bar in the window — that's the
        # opening 1-minute candle whose color sets the bias per the
        # Zarattini design (and Manny's spec).
        first = opening_bars[0]
        if self.use_5min_direction_bias:
            if first.close > first.open:
                bias = "long"
            elif first.close < first.open:
                bias = "short"
            else:
                bias = "neutral"
        else:
            bias = "neutral"

        meta = {
            "direction_bias": bias,
            "opening_range_minutes": self.minutes,
            "opening_range_volume": sum(b.volume for b in opening_bars),
            "opening_range_first_open": first.open,
            "opening_range_first_close": first.close,
            "opening_range_high": orh,
            "opening_range_low": orl,
        }

        levels = (
            Level(price=orh, kind="ORH", session_date=session_date, metadata=meta),
            Level(price=orl, kind="ORL", session_date=session_date, metadata=meta),
        )
        return LevelSet(symbol=symbol, session_date=session_date, levels=levels)

    def update_intraday(self, bar: Bar) -> None:
        """No-op. Opening range is fixed once the first N minutes have closed."""
        return None

    # ----- helpers --------------------------------------------------------

    def _opening_bars(self, bars: list[Bar]) -> list[Bar]:
        """Return the bars that fall in the [09:30, 09:30 + minutes) ET window.

        Bars are assumed to be chronologically ordered. We:
        1. Locate the first bar whose minute-of-day equals 09:30 ET
           (or the UTC analogues if session_open_local=False).
        2. Walk forward, accepting bars whose timestamps are within
           `minutes` minutes of that anchor (strict less-than).
        """
        # Locate the 09:30 anchor.
        anchor_idx = self._anchor_index(bars)
        if anchor_idx is None:
            return []
        anchor_ts = bars[anchor_idx].timestamp
        window_end = anchor_ts + timedelta(minutes=self.minutes)

        out: list[Bar] = []
        for b in bars[anchor_idx:]:
            if b.timestamp >= window_end:
                break
            out.append(b)
        return out

    def _anchor_index(self, bars: list[Bar]) -> Optional[int]:
        """Return the index of the first bar at 09:30 ET (or its UTC equivalent)."""
        if self.session_open_local:
            for i, b in enumerate(bars):
                if b.timestamp.time() == _MARKET_OPEN_ET:
                    return i
        else:
            for i, b in enumerate(bars):
                mod = b.timestamp.hour * 60 + b.timestamp.minute
                if mod in (_OPEN_MINUTE_UTC_EST, _OPEN_MINUTE_UTC_EDT):
                    return i
        return None


__all__ = ["OpeningRangeSource"]
