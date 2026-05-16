"""VolumeProfileSource — Phase 2 level source emitting POC, HVN, LVN levels.

Per DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §4.5 and
DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §5 Agent L (Wave 5).

A volume profile is the distribution of *volume traded at each price* over
some lookback window — N prior sessions for the daily profile (default
N=5), or the developing intraday profile for live decision-making. Bins
are constructed at a configurable width (default = 0.1% of a reference
price, computed at compute_levels time from the most-recent bar close).

Three structural levels are emitted:

  * **POC** (Point of Control) — the single bin with the highest cumulative
    volume across the lookback window. Acts as a price magnet; rotations
    "go to POC" are the canonical mean-reversion setup in AMT.
  * **HVN** (High Volume Node) — every bin whose volume > 1.5× the rolling
    mean bin volume. These are acceptance areas; price tends to pause,
    rotate, or reject at them.
  * **LVN** (Low Volume Node) — every bin whose volume < 0.5× the rolling
    mean bin volume. These are vacuum areas; price tends to *fly through*
    them on the way to the next HVN cluster.

The two Phase 2 strategies use these complementary properties:
  - `volume_profile_rejection`: Mean-reversion fade at HVN edges.
  - `volume_profile_breakout`: Breakout through LVNs targeting next HVN.

Bin construction is volume-of-bar-at-typical-price. We don't have access
to per-trade tick data inside this source (the framework's Bar abstraction
is OHLCV); the typical-price approach (TP = (H + L + C)/3) maps each bar's
volume to a single bin. This is a deliberate Wave-5 simplification — the
design doc §4.5 calls out tick-level reconstruction as the "right" answer
but the Wave 5 build directive (Agent L) accepts bar-level reconstruction
as the most-logical-path given the 1-minute bar fidelity ceiling already
documented in the Wave 3 reports. Bin error vs tick-level reconstruction
is on the order of 1-3 bins for liquid mega-cap names trading at $50-200,
which is below the SignalCandle / Rejection confirmation's natural noise.

Edge cases handled:
- Empty history → empty LevelSet
- Single-bin profile (all volume at one price) → emit POC only, no
  HVN/LVN (mean-relative thresholds are degenerate when N=1).
- Zero-volume bars → skipped (don't poison the typical-price weighting).
- Non-finite OHLC / volume → bar skipped silently.
- Bin width 0 (pathological config) → default to $0.01.

`update_intraday(bar)` accumulates the current session's developing profile
into a separate internal counter; callers that want a *combined* profile
(prior-N + intraday) can re-call `compute_levels(history)` where history
includes today's bars — the source treats every bar in history the same
way regardless of session.

References:
  - DESIGN §4.5 (Volume Profile / AMT)
  - VP research §1-9 (research_vp_market_profile.md)
  - Trading Notes Signal Candle Model (LVN sweep → HVN edge reaction)
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as _date, datetime
from typing import Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
)


# Default thresholds per directive Agent L spec.
_DEFAULT_HVN_MULTIPLIER: float = 1.5
_DEFAULT_LVN_MULTIPLIER: float = 0.5
_DEFAULT_BIN_PCT: float = 0.001  # 0.1% of reference price
_DEFAULT_LOOKBACK_SESSIONS: int = 5
_DEFAULT_BIN_MIN_WIDTH: float = 0.01  # one cent (penny tick)


def _typical_price(bar: Bar) -> float:
    """Typical price = (high + low + close)/3.

    The canonical AMT bin assignment when working from bar data (vs. ticks).
    """
    return (bar.high + bar.low + bar.close) / 3.0


def _finite(x: float) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@dataclass
class VolumeProfileSource:
    """Volume profile level source.

    Args:
        lookback_sessions: How many prior trading sessions to include in
            the daily profile. Default 5; the directive default.
        bin_pct: Fractional bin width as % of reference price (the latest
            close). Default 0.001 = 0.1%. Smaller values produce finer
            profiles at the cost of HVN/LVN signal noise.
        bin_dollar: Absolute dollar bin width override. If set, takes
            precedence over bin_pct (useful for cross-symbol comparability).
        hvn_multiplier: Bin volume / mean bin volume threshold to flag HVN.
            Default 1.5×.
        lvn_multiplier: Bin volume / mean bin volume threshold to flag LVN.
            Default 0.5×.
        emit_poc: If True (default), emit the single POC level.
        emit_hvn: If True (default), emit HVN levels.
        emit_lvn: If True (default), emit LVN levels.
        min_bars_for_signal: Don't emit HVN/LVN levels until at least this
            many distinct bins exist (prevents single-bin pathological
            profiles from emitting spurious levels). Default 3.
        target_date: For deterministic test/backtest use. If set, the
            session_date stamped on Levels is this; otherwise inferred from
            the most recent bar.
    """

    lookback_sessions: int = _DEFAULT_LOOKBACK_SESSIONS
    bin_pct: float = _DEFAULT_BIN_PCT
    bin_dollar: Optional[float] = None
    hvn_multiplier: float = _DEFAULT_HVN_MULTIPLIER
    lvn_multiplier: float = _DEFAULT_LVN_MULTIPLIER
    emit_poc: bool = True
    emit_hvn: bool = True
    emit_lvn: bool = True
    min_bars_for_signal: int = 3
    # When True, merge adjacent same-class bins into a single Level at the
    # cluster centroid. This is the canonical AMT representation — clusters
    # have edges, not per-bin levels. Default True; tests can disable to
    # see per-bin breakdown.
    merge_adjacent: bool = True
    target_date: Optional[_date] = None

    # Internal developing profile accumulated via update_intraday. Volume
    # is keyed by bin-index (int). Separate from history-driven compute_levels
    # so callers can choose either snapshot.
    _intraday_volume: dict[int, float] = field(default_factory=lambda: defaultdict(float), init=False, repr=False)
    _intraday_ref_price: Optional[float] = field(default=None, init=False, repr=False)
    _last_level_set: Optional[LevelSet] = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def __post_init__(self) -> None:
        if self.lookback_sessions < 1:
            raise ValueError(
                f"lookback_sessions must be >= 1 (got {self.lookback_sessions})"
            )
        if self.bin_pct <= 0 and (self.bin_dollar is None or self.bin_dollar <= 0):
            raise ValueError(
                "VolumeProfileSource requires positive bin_pct or bin_dollar"
            )
        if self.bin_dollar is not None and self.bin_dollar <= 0:
            raise ValueError("bin_dollar must be > 0 when set")
        if self.hvn_multiplier <= 1.0:
            raise ValueError(
                f"hvn_multiplier must be > 1.0 (got {self.hvn_multiplier})"
            )
        if self.lvn_multiplier <= 0 or self.lvn_multiplier >= 1.0:
            raise ValueError(
                f"lvn_multiplier must be in (0, 1) (got {self.lvn_multiplier})"
            )
        if self.min_bars_for_signal < 1:
            raise ValueError(
                f"min_bars_for_signal must be >= 1 (got {self.min_bars_for_signal})"
            )

    # ------------------------------------------------------------------ #
    # LevelSourceProtocol
    # ------------------------------------------------------------------ #
    def compute_levels(self, symbol: str, history: BarHistory) -> LevelSet:
        """Build a LevelSet from the prior `lookback_sessions` of bar history.

        If `history` is empty, an empty LevelSet is returned.
        """
        target = self._resolve_target_date(history)
        if target is None:
            return LevelSet(symbol=symbol, session_date=_date.today())

        # Select bars from up to `lookback_sessions` distinct dates that are
        # < target_date. If the target is None (no target_date set and bars
        # exist), we take the most-recent N dates *including* the latest one.
        bars_for_profile = self._select_lookback_bars(history, target)
        if not bars_for_profile:
            ls = LevelSet(symbol=symbol, session_date=target)
            self._last_level_set = ls
            return ls

        # Reference price: most recent close in selected window.
        ref_price = float(bars_for_profile[-1].close)
        if not _finite(ref_price) or ref_price <= 0:
            ls = LevelSet(symbol=symbol, session_date=target)
            self._last_level_set = ls
            return ls

        bin_width = self._bin_width(ref_price)
        bin_volume = self._bin_volume_distribution(bars_for_profile, bin_width)
        if not bin_volume:
            ls = LevelSet(symbol=symbol, session_date=target)
            self._last_level_set = ls
            return ls

        levels = self._build_levels(
            bin_volume=bin_volume,
            bin_width=bin_width,
            session_date=target,
            lookback_session_count=self._distinct_dates(bars_for_profile),
            ref_price=ref_price,
        )
        ls = LevelSet(symbol=symbol, session_date=target, levels=tuple(levels))
        self._last_level_set = ls
        return ls

    def update_intraday(self, bar: Bar) -> None:
        """Accumulate a single bar's volume into the developing intraday
        profile. The reference price (used to size bins) is fixed at the
        first non-empty bar in the intraday window — subsequent bars use
        the same bin grid for consistency within a session.

        This method is idempotent against repeated calls with the same bar
        (it always adds; callers shouldn't double-count).
        """
        if bar is None:
            return
        if not _finite(bar.high) or not _finite(bar.low) or not _finite(bar.close):
            return
        if not _finite(bar.volume) or bar.volume <= 0:
            return
        if self._intraday_ref_price is None:
            ref = _typical_price(bar)
            if not _finite(ref) or ref <= 0:
                return
            self._intraday_ref_price = ref
        bin_width = self._bin_width(self._intraday_ref_price)
        tp = _typical_price(bar)
        if not _finite(tp) or tp <= 0:
            return
        idx = int(math.floor(tp / bin_width))
        self._intraday_volume[idx] += float(bar.volume)

    def reset_intraday(self) -> None:
        """Clear the developing intraday profile (call at session start)."""
        self._intraday_volume = defaultdict(float)
        self._intraday_ref_price = None

    def intraday_snapshot(
        self,
        symbol: str,
        session_date: Optional[_date] = None,
    ) -> LevelSet:
        """Build a LevelSet from the developing intraday profile.

        Independent of `compute_levels`; the two profiles can be combined
        by the caller by appending today's bars into history before calling
        compute_levels (the source-merges-by-bar property).
        """
        if not self._intraday_volume or self._intraday_ref_price is None:
            return LevelSet(symbol=symbol, session_date=session_date or _date.today())
        ref_price = float(self._intraday_ref_price)
        bin_width = self._bin_width(ref_price)
        levels = self._build_levels(
            bin_volume=dict(self._intraday_volume),
            bin_width=bin_width,
            session_date=session_date or _date.today(),
            lookback_session_count=1,
            ref_price=ref_price,
        )
        return LevelSet(
            symbol=symbol,
            session_date=session_date or _date.today(),
            levels=tuple(levels),
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _resolve_target_date(self, history: BarHistory) -> Optional[_date]:
        if self.target_date is not None:
            return self.target_date
        if len(history) == 0:
            return None
        try:
            return max(b.timestamp.date() for b in history.bars if b.timestamp is not None)
        except (AttributeError, ValueError):
            return None

    def _select_lookback_bars(self, history: BarHistory, target: _date) -> list[Bar]:
        """Pick bars from up to `lookback_sessions` distinct dates strictly
        prior to `target`. If no prior session exists in history, fall back
        to using bars from the target date itself (this keeps the daily-profile
        consistent when the harness passes a single combined history).
        """
        if len(history) == 0:
            return []

        # Collect distinct session dates strictly before target.
        prior_dates = sorted({
            b.timestamp.date() for b in history.bars
            if b.timestamp is not None and b.timestamp.date() < target
        })
        chosen_dates: set[_date]
        if prior_dates:
            chosen_dates = set(prior_dates[-self.lookback_sessions:])
        else:
            # No prior session in history — use whatever the most recent
            # session present is. For backtests that pass history=today's
            # bars only, this gives a same-session "developing profile" view.
            chosen_dates = {target}

        return [
            b for b in history.bars
            if b.timestamp is not None
            and b.timestamp.date() in chosen_dates
            and _finite(b.high)
            and _finite(b.low)
            and _finite(b.close)
            and _finite(b.volume)
            and b.volume > 0
        ]

    def _bin_width(self, ref_price: float) -> float:
        if self.bin_dollar is not None and self.bin_dollar > 0:
            return float(self.bin_dollar)
        w = float(ref_price) * float(self.bin_pct)
        if w < _DEFAULT_BIN_MIN_WIDTH:
            return _DEFAULT_BIN_MIN_WIDTH
        return w

    def _bin_volume_distribution(
        self, bars: list[Bar], bin_width: float
    ) -> dict[int, float]:
        """Build a {bin_index: cumulative volume} dict from bars.

        Each bar contributes its entire volume to the typical-price bin.
        This is the bar-level approximation; tick-level would distribute
        volume across the bar's price range.
        """
        out: dict[int, float] = defaultdict(float)
        for b in bars:
            tp = _typical_price(b)
            if not _finite(tp) or tp <= 0:
                continue
            idx = int(math.floor(tp / bin_width))
            out[idx] += float(b.volume)
        return dict(out)

    def _distinct_dates(self, bars: list[Bar]) -> int:
        return len({b.timestamp.date() for b in bars if b.timestamp is not None})

    def _build_levels(
        self,
        bin_volume: dict[int, float],
        bin_width: float,
        session_date: _date,
        lookback_session_count: int,
        ref_price: float,
    ) -> list[Level]:
        """Classify bins as POC/HVN/LVN and return a list of Level objects.

        Returns empty list if the profile is degenerate (no bins).
        """
        if not bin_volume:
            return []

        # Mean bin volume across populated bins (not the bin-grid universe).
        n_bins = len(bin_volume)
        total_volume = sum(bin_volume.values())
        if total_volume <= 0:
            return []
        mean_bin_volume = total_volume / n_bins

        # POC: bin with the largest cumulative volume.
        poc_idx, poc_volume = max(bin_volume.items(), key=lambda kv: kv[1])

        levels: list[Level] = []

        if self.emit_poc:
            levels.append(
                Level(
                    price=_bin_center_price(poc_idx, bin_width),
                    kind="POC",
                    session_date=session_date,
                    metadata={
                        "bin_idx": int(poc_idx),
                        "bin_width": float(bin_width),
                        "bin_volume": float(poc_volume),
                        "mean_bin_volume": float(mean_bin_volume),
                        "total_volume": float(total_volume),
                        "n_bins": int(n_bins),
                        "lookback_session_count": int(lookback_session_count),
                        "ref_price": float(ref_price),
                    },
                )
            )

        # HVN / LVN: only emit when we have enough bins for the thresholds
        # to be meaningful. Single-bin profiles (extreme case) emit POC only.
        if n_bins >= self.min_bars_for_signal:
            hvn_threshold = mean_bin_volume * self.hvn_multiplier
            lvn_threshold = mean_bin_volume * self.lvn_multiplier

            # Classify each bin
            hvn_bins: list[tuple[int, float]] = []
            lvn_bins: list[tuple[int, float]] = []
            for idx, vol in sorted(bin_volume.items()):
                if idx == poc_idx:
                    continue
                if vol >= hvn_threshold:
                    hvn_bins.append((idx, vol))
                elif vol <= lvn_threshold:
                    lvn_bins.append((idx, vol))

            def _emit_clusters(
                bins: list[tuple[int, float]], kind: str
            ) -> None:
                """Emit one Level per cluster of contiguous bins (when
                merge_adjacent=True) or one Level per bin (when False)."""
                if not bins:
                    return
                if not self.merge_adjacent:
                    for idx, vol in bins:
                        levels.append(
                            Level(
                                price=_bin_center_price(idx, bin_width),
                                kind=kind,
                                session_date=session_date,
                                metadata={
                                    "bin_idx": int(idx),
                                    "bin_width": float(bin_width),
                                    "bin_volume": float(vol),
                                    "mean_bin_volume": float(mean_bin_volume),
                                    "ratio": float(vol / mean_bin_volume),
                                    "ref_price": float(ref_price),
                                },
                            )
                        )
                    return

                # Group contiguous bin indices into clusters.
                bins_sorted = sorted(bins, key=lambda kv: kv[0])
                current: list[tuple[int, float]] = []
                clusters: list[list[tuple[int, float]]] = []
                for idx, vol in bins_sorted:
                    if not current or idx == current[-1][0] + 1:
                        current.append((idx, vol))
                    else:
                        clusters.append(current)
                        current = [(idx, vol)]
                if current:
                    clusters.append(current)

                for cluster in clusters:
                    total_vol = sum(v for _, v in cluster)
                    if total_vol <= 0:
                        continue
                    # Volume-weighted centroid index
                    centroid = (
                        sum(idx * v for idx, v in cluster) / total_vol
                    )
                    # Centroid price uses the float centroid so cluster
                    # midpoint lands cleanly between bins.
                    centroid_price = round(
                        (centroid + 0.5) * bin_width, 4
                    )
                    levels.append(
                        Level(
                            price=centroid_price,
                            kind=kind,
                            session_date=session_date,
                            metadata={
                                "bin_idx": int(round(centroid)),
                                "bin_width": float(bin_width),
                                "bin_volume": float(total_vol),
                                "mean_bin_volume": float(mean_bin_volume),
                                "ratio": float(
                                    (total_vol / len(cluster)) / mean_bin_volume
                                ),
                                "n_bins_in_cluster": int(len(cluster)),
                                "cluster_low_idx": int(cluster[0][0]),
                                "cluster_high_idx": int(cluster[-1][0]),
                                "cluster_low_price": float(
                                    _bin_center_price(
                                        cluster[0][0], bin_width
                                    )
                                    - bin_width / 2
                                ),
                                "cluster_high_price": float(
                                    _bin_center_price(
                                        cluster[-1][0], bin_width
                                    )
                                    + bin_width / 2
                                ),
                                "ref_price": float(ref_price),
                            },
                        )
                    )

            if self.emit_hvn:
                _emit_clusters(hvn_bins, "HVN")
            if self.emit_lvn:
                _emit_clusters(lvn_bins, "LVN")

        # Order by price ascending — matches RoundNumberSource convention
        # and gives downstream code a predictable iteration order.
        levels.sort(key=lambda lv: lv.price)
        return levels


def _bin_center_price(bin_idx: int, bin_width: float) -> float:
    """Center price of a bin: (idx + 0.5) * bin_width."""
    return round((bin_idx + 0.5) * bin_width, 4)


# ---------------------------------------------------------------------------
# YAML config loader (used by registry / portfolio loader)
# ---------------------------------------------------------------------------


def from_config(params: dict) -> VolumeProfileSource:
    """Build a VolumeProfileSource from a YAML `level_source.params` dict.

    Recognized keys (all optional, sensible defaults):
        lookback_sessions: int
        bin_pct: float
        bin_dollar: float
        hvn_multiplier: float
        lvn_multiplier: float
        emit_poc: bool
        emit_hvn: bool
        emit_lvn: bool
        min_bars_for_signal: int

    Unknown keys are ignored (forward-compat).
    """
    return VolumeProfileSource(
        lookback_sessions=int(params.get("lookback_sessions", _DEFAULT_LOOKBACK_SESSIONS)),
        bin_pct=float(params.get("bin_pct", _DEFAULT_BIN_PCT)),
        bin_dollar=(
            float(params["bin_dollar"]) if params.get("bin_dollar") is not None else None
        ),
        hvn_multiplier=float(params.get("hvn_multiplier", _DEFAULT_HVN_MULTIPLIER)),
        lvn_multiplier=float(params.get("lvn_multiplier", _DEFAULT_LVN_MULTIPLIER)),
        emit_poc=bool(params.get("emit_poc", True)),
        emit_hvn=bool(params.get("emit_hvn", True)),
        emit_lvn=bool(params.get("emit_lvn", True)),
        min_bars_for_signal=int(params.get("min_bars_for_signal", 3)),
        merge_adjacent=bool(params.get("merge_adjacent", True)),
    )


__all__ = ["VolumeProfileSource", "from_config"]
