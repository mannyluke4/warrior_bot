"""wave_detector.py — Wave Scalp Stage 1 pattern detection (no trading logic).

Identifies oscillation waves on a 1-minute bar stream. A "wave" per
DIRECTIVE_WAVE_SCALP_STAGE1_RESEARCH.md:

  - A price swing of at least `min_magnitude_pct` (default 0.75%) from a
    local extreme (high or low)
  - Duration between the start and end pivots is in `[min_duration_min,
    max_duration_min]` (default 3–15 min)
  - Confirmation: must be followed by a reversal of at least
    `min_reversal_pct` (default 0.5%) in the opposite direction

The detector operates on closed 1-minute bars and is purely descriptive —
it labels waves; it does NOT generate trade signals or score setups (that
lives in the census/scoring driver, separate from this file).

Internal state machine (ZigZag-pivot style):
  - We carry one anchor pivot (`anchor`) — the last confirmed turning point.
  - We track the current `running_extreme` — the most-extended bar in the
    current direction since the anchor.
  - On each new bar we extend the running extreme if it makes a new high/low
    in our direction, then check whether price has reversed by at least
    `min_reversal_pct` from the running extreme. If so, the swing from
    anchor → running_extreme is a candidate wave.
  - The candidate wave is emitted iff (a) magnitude from anchor to extreme
    is ≥ `min_magnitude_pct`, and (b) the elapsed minutes is in the duration
    band. If duration is out of band the swing is silently dropped (we
    still re-anchor so detection continues) — this matches the directive's
    "wave is only a wave if it fits the spec" framing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class _Pivot:
    """Internal pivot point — the start or end of a wave."""
    time_utc: datetime
    price: float
    bar_index: int  # index into the bar history this detector has seen


@dataclass
class _RunningExtreme:
    """Most-extended bar in the current direction since the anchor."""
    time_utc: datetime
    price: float
    bar_index: int


class WaveDetector:
    """Stateful wave detector for a single symbol.

    Feed it 1-minute Bar objects via `on_bar_close(bar)`. Each call returns
    either `None` (no wave just confirmed) or a wave dict (matching the
    directive's required output shape).
    """

    def __init__(
        self,
        symbol: str,
        *,
        min_magnitude_pct: float = 0.75,
        min_reversal_pct: float = 0.5,
        min_duration_min: int = 3,
        max_duration_min: int = 15,
    ):
        self.symbol = symbol
        self.min_magnitude_pct = float(min_magnitude_pct)
        self.min_reversal_pct = float(min_reversal_pct)
        self.min_duration_min = int(min_duration_min)
        self.max_duration_min = int(max_duration_min)

        # State
        self._anchor: Optional[_Pivot] = None
        self._extreme: Optional[_RunningExtreme] = None
        # 'up' = we're tracking a rising swing (looking for higher highs);
        # 'down' = we're tracking a falling swing.
        self._direction: Optional[str] = None

        # Per-detector ID for waves emitted; resets on `reset()`.
        self._next_wave_id = 1

        # Bar history — indexed by bar_index. Used to compute volume
        # statistics (max_volume_bar, avg_volume) over the wave's span.
        self._bars: List[dict] = []
        # Cumulative volume sum prefix for fast slice-mean. _vol_prefix[i]
        # = sum of volumes for bars[0..i-1].
        self._vol_prefix: List[int] = [0]

    def reset(self) -> None:
        """Clear all state. Use between dates when running batch census."""
        self._anchor = None
        self._extreme = None
        self._direction = None
        self._next_wave_id = 1
        self._bars.clear()
        self._vol_prefix = [0]

    # ── Public API ──────────────────────────────────────────────────────
    def on_bar_close(self, bar) -> Optional[dict]:
        """Process a closed 1m bar. Returns a wave dict if one just confirmed,
        else None.

        `bar` must expose `.start_utc` (datetime, UTC), `.open/.high/.low/.close`
        (floats), and `.volume` (int). The `bars.Bar` dataclass satisfies this.
        """
        bar_index = len(self._bars)
        self._bars.append({
            "start_utc": bar.start_utc,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": int(bar.volume),
        })
        self._vol_prefix.append(self._vol_prefix[-1] + int(bar.volume))

        # Bootstrap: first bar — anchor here, direction unknown until we see
        # the second bar.
        if self._anchor is None:
            self._anchor = _Pivot(
                time_utc=bar.start_utc, price=float(bar.close),
                bar_index=bar_index,
            )
            self._extreme = _RunningExtreme(
                time_utc=bar.start_utc, price=float(bar.close),
                bar_index=bar_index,
            )
            return None

        # Determine direction on the second bar based on initial movement.
        if self._direction is None:
            if bar.close > self._anchor.price:
                self._direction = "up"
                self._extreme = _RunningExtreme(
                    time_utc=bar.start_utc, price=float(bar.high),
                    bar_index=bar_index,
                )
            elif bar.close < self._anchor.price:
                self._direction = "down"
                self._extreme = _RunningExtreme(
                    time_utc=bar.start_utc, price=float(bar.low),
                    bar_index=bar_index,
                )
            # If close == anchor exactly, stay undirected and try next bar.
            return None

        # Steady-state: extend running extreme in current direction or check
        # for reversal that confirms a wave.
        if self._direction == "up":
            # Extend up?
            if bar.high > self._extreme.price:
                self._extreme = _RunningExtreme(
                    time_utc=bar.start_utc, price=float(bar.high),
                    bar_index=bar_index,
                )
            # Reversal check: low must drop ≥ min_reversal_pct from extreme.
            reversal_threshold = self._extreme.price * (1.0 - self.min_reversal_pct / 100.0)
            if bar.low <= reversal_threshold:
                wave = self._maybe_emit_wave(direction="up", current_bar_index=bar_index)
                # Re-anchor at the running extreme regardless of emission;
                # current bar starts the new (down) swing.
                self._anchor = _Pivot(
                    time_utc=self._extreme.time_utc, price=self._extreme.price,
                    bar_index=self._extreme.bar_index,
                )
                self._direction = "down"
                self._extreme = _RunningExtreme(
                    time_utc=bar.start_utc, price=float(bar.low),
                    bar_index=bar_index,
                )
                return wave

        else:  # direction == "down"
            if bar.low < self._extreme.price:
                self._extreme = _RunningExtreme(
                    time_utc=bar.start_utc, price=float(bar.low),
                    bar_index=bar_index,
                )
            reversal_threshold = self._extreme.price * (1.0 + self.min_reversal_pct / 100.0)
            if bar.high >= reversal_threshold:
                wave = self._maybe_emit_wave(direction="down", current_bar_index=bar_index)
                self._anchor = _Pivot(
                    time_utc=self._extreme.time_utc, price=self._extreme.price,
                    bar_index=self._extreme.bar_index,
                )
                self._direction = "up"
                self._extreme = _RunningExtreme(
                    time_utc=bar.start_utc, price=float(bar.high),
                    bar_index=bar_index,
                )
                return wave

        return None

    # ── Internals ───────────────────────────────────────────────────────
    def _maybe_emit_wave(self, *, direction: str, current_bar_index: int) -> Optional[dict]:
        """Decide whether the just-completed swing meets the wave spec
        and, if so, build and return the wave dict."""
        anchor = self._anchor
        extreme = self._extreme
        if anchor is None or extreme is None:
            return None

        magnitude_dollars = abs(extreme.price - anchor.price)
        # Magnitude pct relative to the anchor (matches "swing of ≥ X% from
        # the local extreme" wording — anchor IS the prior local extreme).
        magnitude_pct = (magnitude_dollars / anchor.price) * 100.0 if anchor.price > 0 else 0.0

        duration_seconds = (extreme.time_utc - anchor.time_utc).total_seconds()
        duration_minutes = duration_seconds / 60.0

        # Specification gates:
        #   1. Magnitude must clear the threshold.
        #   2. Duration must be in the band.
        if magnitude_pct < self.min_magnitude_pct:
            return None
        if duration_minutes < self.min_duration_min:
            return None
        if duration_minutes > self.max_duration_min:
            return None

        # Volume stats over [anchor.bar_index, extreme.bar_index] inclusive.
        i0 = anchor.bar_index
        i1 = extreme.bar_index
        if i1 < i0:
            i0, i1 = i1, i0
        span_bars = self._bars[i0 : i1 + 1]
        if span_bars:
            volumes = [b["volume"] for b in span_bars]
            max_volume_bar = max(volumes)
            avg_volume = sum(volumes) / len(volumes)
        else:
            max_volume_bar = 0
            avg_volume = 0.0

        wave = {
            "symbol": self.symbol,
            "wave_id": self._next_wave_id,
            "direction": direction,
            "start_time_utc": anchor.time_utc.isoformat(),
            "start_price": round(anchor.price, 4),
            "end_time_utc": extreme.time_utc.isoformat(),
            "end_price": round(extreme.price, 4),
            "duration_minutes": round(duration_minutes, 2),
            "magnitude_pct": round(magnitude_pct, 4),
            "magnitude_dollars": round(magnitude_dollars, 4),
            "max_volume_bar": int(max_volume_bar),
            "avg_volume": round(avg_volume, 1),
            # Bar-index span — useful for downstream scoring / setup detection.
            "anchor_bar_index": anchor.bar_index,
            "extreme_bar_index": extreme.bar_index,
        }
        self._next_wave_id += 1
        return wave

    # ── Read-only accessors used by downstream scoring ─────────────────
    @property
    def bars(self) -> List[dict]:
        """All bars seen by this detector (useful for scoring/debugging)."""
        return self._bars

    def avg_volume_last_n(self, n: int, end_bar_index: Optional[int] = None) -> float:
        """Average volume of the last `n` bars ending at `end_bar_index`
        (inclusive). If end_bar_index is None, uses the most recent bar.
        Returns 0.0 when fewer than `n` bars are available."""
        if end_bar_index is None:
            end_bar_index = len(self._bars) - 1
        if end_bar_index < 0 or n <= 0:
            return 0.0
        start = end_bar_index - n + 1
        if start < 0:
            return 0.0
        # _vol_prefix[i] = sum of bars[0..i-1]; sum over [start..end] is
        # prefix[end+1] - prefix[start].
        total = self._vol_prefix[end_bar_index + 1] - self._vol_prefix[start]
        return total / n
