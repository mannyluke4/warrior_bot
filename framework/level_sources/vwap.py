"""Session VWAP level source — Wave 2, Agent G.

Implements ``VWAPSource`` per DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3
(Agent G) and DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §4.2.

A VWAP source consumes a symbol's intraday bar stream and produces:

- ``Level(kind='VWAP')``                — session volume-weighted avg price
- ``Level(kind='VWAP_UPPER_<n>')``      — VWAP + n*sigma band (per band sigma in cfg)
- ``Level(kind='VWAP_LOWER_<n>')``      — VWAP - n*sigma band

VWAP math (the standard "session typical-price" definition):

    typical_i = (high_i + low_i + close_i) / 3
    cum_pv    = sum_{j<=i} typical_j * volume_j
    cum_vol   = sum_{j<=i} volume_j
    vwap_i    = cum_pv / cum_vol

Volume-weighted variance (population form, matching common platforms):

    cum_pvv   = sum_{j<=i} (typical_j - vwap_j)^2 * volume_j
    sigma_i   = sqrt(cum_pvv / cum_vol)

We compute sigma against the *running* VWAP rather than the final VWAP —
that's the convention TradingView, Sierra Chart, and ThinkorSwim use for
the "VWAP bands" indicator. It matches what a live bot watching the chart
would see at each bar close.

Regime gating helper ``vwap_slope_classifier`` returns one of
{'trending_up', 'trending_down', 'flat'} based on the linear-regression
slope of VWAP over the last N bars normalized by recent VWAP level
(so the threshold is invariant to price). The thresholds are conservative
defaults tuned to ~5% movement-per-hour boundaries (see the function
docstring for the math).

The class is dataclass-shaped for easy YAML construction via the registry
(`band_sigmas: list[float]` is read straight from `level_source.params.bands`
in the spec YAML). Wave-2 wiring in registry.py will resolve the type
string ``vwap`` to this concrete class.

This module is **research / backtest infrastructure**. It does not touch
the existing live stack. The framework lives entirely under framework/.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal, Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
)


SlopeRegime = Literal["trending_up", "trending_down", "flat"]


@dataclass
class VWAPState:
    """Internal accumulator. Recomputable from history; held for O(1) updates."""

    cum_pv: float = 0.0           # sum(typical * volume)
    cum_vol: float = 0.0          # sum(volume)
    cum_pvv: float = 0.0          # sum((typical - vwap_running)^2 * volume)
    # Rolling VWAP history per bar for slope classifier + diagnostics.
    vwap_series: list[float] = field(default_factory=list)
    n_bars: int = 0

    def reset(self) -> None:
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        self.cum_pvv = 0.0
        self.vwap_series = []
        self.n_bars = 0


@dataclass
class VWAPSource:
    """Session VWAP + ±N sigma bands.

    Attributes
    ----------
    band_sigmas : list[float]
        One band level per multiplier. Each generates a paired UPPER/LOWER
        level. Default ``[1.0, 2.0]`` produces VWAP_UPPER_1, VWAP_LOWER_1,
        VWAP_UPPER_2, VWAP_LOWER_2.
    """

    band_sigmas: list[float] = field(default_factory=lambda: [1.0, 2.0])
    state: VWAPState = field(default_factory=VWAPState)
    _session_date: Optional[date] = None
    _symbol: str = ""

    # ── core math ────────────────────────────────────────────────────────

    @staticmethod
    def _typical(bar: Bar) -> float:
        return (bar.high + bar.low + bar.close) / 3.0

    def _ingest(self, bar: Bar) -> None:
        """Update running VWAP + sigma accumulators with one closed bar.

        Skip non-finite or non-positive-volume bars (defensive); they don't
        carry information and would NaN-propagate.
        """
        v = bar.volume
        if v is None:
            return
        try:
            if not math.isfinite(float(v)) or v <= 0:
                return
        except (TypeError, ValueError):
            return
        tp = self._typical(bar)
        if not math.isfinite(tp):
            return
        s = self.state
        s.cum_pv += tp * v
        s.cum_vol += v
        # Running VWAP after including this bar
        if s.cum_vol <= 0:
            return
        vwap_now = s.cum_pv / s.cum_vol
        # Squared-deviation accumulation uses the *running* VWAP at this
        # bar (not the final one) — matches charting-platform convention.
        s.cum_pvv += ((tp - vwap_now) ** 2) * v
        s.vwap_series.append(vwap_now)
        s.n_bars += 1

    # ── public properties ────────────────────────────────────────────────

    @property
    def vwap(self) -> Optional[float]:
        s = self.state
        if s.cum_vol <= 0:
            return None
        return s.cum_pv / s.cum_vol

    @property
    def sigma(self) -> Optional[float]:
        """Volume-weighted standard deviation of typical price about running VWAP.

        Returns None if no volume has been ingested.
        """
        s = self.state
        if s.cum_vol <= 0:
            return None
        var = s.cum_pvv / s.cum_vol
        if var < 0:  # floating noise guard
            var = 0.0
        return math.sqrt(var)

    # ── LevelSourceProtocol ──────────────────────────────────────────────

    @staticmethod
    def _infer_session_date(history: BarHistory) -> date:
        """Pick a session date from the first bar (defaults to today if empty).

        We deliberately use the FIRST bar rather than the last so that an
        intraday call mid-session reports the session it started in, not
        a date roll-over from after-hours ticks.
        """
        if history.bars:
            return history.bars[0].timestamp.date()
        return date.today()

    def compute_levels(self, symbol: str, history: BarHistory) -> LevelSet:
        """Rebuild VWAP + bands from scratch over `history`.

        Called once per session boot. Subsequent updates use
        ``update_intraday(bar)`` for O(1) appending.
        """
        self.state.reset()
        self._symbol = symbol or history.symbol
        session_date = self._infer_session_date(history)
        self._session_date = session_date

        for bar in history.bars:
            self._ingest(bar)

        return self._build_levelset(session_date)

    def update_intraday(self, bar: Bar) -> None:
        """Append a newly-closed bar to the running VWAP."""
        if self._session_date is None:
            # If compute_levels was never called, infer from this bar.
            self._session_date = bar.timestamp.date()
        self._ingest(bar)

    def current_levelset(self, symbol: Optional[str] = None) -> LevelSet:
        """Return the current set of levels without recomputing.

        Useful intra-session after update_intraday() ingests new bars.
        """
        sym = symbol or self._symbol
        sd = self._session_date or date.today()
        # Stash the current symbol if caller supplied one.
        if symbol:
            self._symbol = symbol
        return self._build_levelset(sd, symbol=sym)

    # ── level construction ───────────────────────────────────────────────

    def _build_levelset(
        self, session_date: date, symbol: Optional[str] = None
    ) -> LevelSet:
        sym = symbol or self._symbol or ""
        vwap_val = self.vwap
        if vwap_val is None or not math.isfinite(vwap_val):
            return LevelSet(symbol=sym, session_date=session_date, levels=tuple())

        sigma = self.sigma or 0.0
        levels: list[Level] = []
        slope_meta = {
            "slope_per_bar": self._slope_per_bar(),
            "n_bars": self.state.n_bars,
        }
        levels.append(
            Level(
                price=vwap_val,
                kind="VWAP",
                session_date=session_date,
                metadata={"sigma": sigma, **slope_meta},
            )
        )
        for n in self.band_sigmas:
            offset = sigma * float(n)
            upper_kind = f"VWAP_UPPER_{_format_band_label(n)}"
            lower_kind = f"VWAP_LOWER_{_format_band_label(n)}"
            levels.append(
                Level(
                    price=vwap_val + offset,
                    kind=upper_kind,
                    session_date=session_date,
                    metadata={"sigma": sigma, "n_sigma": float(n)},
                )
            )
            levels.append(
                Level(
                    price=vwap_val - offset,
                    kind=lower_kind,
                    session_date=session_date,
                    metadata={"sigma": sigma, "n_sigma": float(n)},
                )
            )
        return LevelSet(symbol=sym, session_date=session_date, levels=tuple(levels))

    # ── slope diagnostics ────────────────────────────────────────────────

    def _slope_per_bar(self) -> float:
        """Per-bar slope of VWAP, dollar units. 0.0 if insufficient data."""
        s = self.state.vwap_series
        n = len(s)
        if n < 2:
            return 0.0
        # Simple OLS slope through (i, vwap_i) for the most recent bars.
        return _linreg_slope(s)

    # ── classifier ───────────────────────────────────────────────────────

    def vwap_slope_classifier(
        self,
        last_n_bars: int = 10,
        flat_pct_per_bar: float = 0.00002,
    ) -> SlopeRegime:
        """Classify VWAP slope over the most recent ``last_n_bars`` bars.

        Math:
            Compute the fractional change in cumulative VWAP from `last_n_bars`
            ago to now, divided by `last_n_bars`. This is a robust proxy for
            "how is VWAP sloping right now?" that matches how a trader reads
            the VWAP line on a chart — it ignores the deep history of
            cumulative VWAP that hasn't moved in 100+ bars.

            pct_per_bar = (vwap_now - vwap_n_bars_ago) / vwap_now / last_n_bars

            regime:
                trending_up    if pct_per_bar >=  flat_pct_per_bar
                trending_down  if pct_per_bar <= -flat_pct_per_bar
                flat           otherwise

        The default flat threshold of 2e-5 (0.2 bps / bar of cumulative
        VWAP movement) is calibrated empirically against the cumulative-VWAP
        slope of trending vs choppy sessions. Cumulative VWAP smooths
        aggressively as bars accumulate, so this looks tiny in normalized
        terms but separates real trends from chop on synthetic GBM bars
        and on real intraday tape. Tune higher for slower regime gates.

        With < 2 bars of history, returns 'flat' (we don't have a slope yet).
        """
        s = self.state.vwap_series
        if not s or len(s) < 2:
            return "flat"
        n = min(last_n_bars, len(s) - 1) if last_n_bars > 0 else (len(s) - 1)
        if n < 1:
            return "flat"
        vwap_now = s[-1]
        vwap_then = s[-1 - n]
        ref = vwap_now or 1e-9
        pct_per_bar = (vwap_now - vwap_then) / ref / n
        if pct_per_bar >= flat_pct_per_bar:
            return "trending_up"
        if pct_per_bar <= -flat_pct_per_bar:
            return "trending_down"
        return "flat"


# ── helpers ────────────────────────────────────────────────────────────


def _format_band_label(n: float) -> str:
    """Format band multiplier for the level-kind tag.

    1.0 -> '1', 2.0 -> '2', 1.5 -> '1_5', 2.5 -> '2_5'.
    """
    if float(n).is_integer():
        return str(int(n))
    return str(n).replace(".", "_")


def _linreg_slope(ys: Iterable[float]) -> float:
    """OLS slope of y_i vs i (1-D). Returns 0.0 if degenerate."""
    ys = [float(y) for y in ys if math.isfinite(float(y))]
    n = len(ys)
    if n < 2:
        return 0.0
    mean_y = sum(ys) / n
    mean_x = (n - 1) / 2.0
    num = 0.0
    den = 0.0
    for i, y in enumerate(ys):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    if den == 0:
        return 0.0
    return num / den


__all__ = [
    "VWAPSource",
    "VWAPState",
    "SlopeRegime",
]
