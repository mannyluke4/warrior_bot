"""RoundNumberSource — whole-dollar / $5 / $10 level generator.

Per DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §4.4 and
DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3 Agent I.

A "round number" is a price psychologically anchored by options strikes,
order-book stacking, and human cognitive bias. Stocks tend to react at
these levels — pause, reverse, or accelerate — far more often than at
arbitrary prices. The strength of the reaction varies by price tier:

  $10-$50    →  whole-dollar AND $5 multiples are sticky
  $50-$150   →  $5 multiples (whole dollars get noisy; share size shrinks)
  $150-$300  →  $5 and $10 multiples (institutional benchmark levels)

This source emits all in-window round numbers around the symbol's
current price. The strategy's ArrivalDetector then watches for the
symbol to touch any of them; SignalCandle confirms; JustPastLevel stops;
target rule projects to the next level up.

Notes on tier resolution
------------------------
A symbol's tier is decided from its `current_price` at compute time. If
a symbol is mid-tier (e.g. price=$48.75 with $10-$50 boundary at $50),
the source uses the tier that the current price falls in. The window
size — ±N dollars / ±N% around the current price — is configurable
via the YAML `window_dollar` or `window_pct` params (one required).

Metadata on each emitted level:
    {
        "tier":       "10_50" | "50_150" | "150_300",
        "increment":  1.00 / 5.00 / 10.00,
        "ref_price":  current_price used to compute the window,
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Iterable, Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
)


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------


# Canonical tier definitions used across the framework. Boundaries are
# closed at the low end, open at the high end (e.g. $10-$50 captures
# prices in [10, 50); $50-$150 captures [50, 150); etc.).
TIER_BOUNDS: dict[str, tuple[float, float]] = {
    "10_50":   (10.0, 50.0),
    "50_150":  (50.0, 150.0),
    "150_300": (150.0, 300.0),
}

# Default increments per tier matching design §4.4 / directive §3 Agent I.
DEFAULT_INCREMENTS: dict[str, list[float]] = {
    "10_50":   [1.00, 5.00],
    "50_150":  [5.00],
    "150_300": [5.00, 10.00],
}


def resolve_tier(price: float) -> Optional[str]:
    """Return the tier key for `price`, or None if outside all tiers.

    Prices outside the $10-$300 universe (sub-$10 or $300+) return None;
    the strategy should not emit signals for them.
    """
    if price <= 0:
        return None
    for key, (lo, hi) in TIER_BOUNDS.items():
        if lo <= price < hi:
            return key
    return None


# ---------------------------------------------------------------------------
# RoundNumberSource — the LevelSourceProtocol implementation
# ---------------------------------------------------------------------------


@dataclass
class RoundNumberSource:
    """Emit round-number levels around a symbol's current price.

    Args:
        increments: Tier-keyed list of dollar increments to emit. Defaults
            to DEFAULT_INCREMENTS. Override per strategy via YAML.
        window_dollar: Absolute dollar half-window around current price.
            If set, emits all increments in [price - window, price + window].
        window_pct: Fractional half-window (e.g. 0.10 = 10% of current price).
            If both window_dollar and window_pct are set, the larger applies.

    At least one of (window_dollar, window_pct) must be set, else the
    source has no idea which levels to emit (the universe of integers in
    [$10, $300] is far too large to emit unconditionally).
    """

    increments: dict[str, list[float]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_INCREMENTS.items()}
    )
    window_dollar: Optional[float] = 5.0     # default ±$5 window — covers all $1/$5/$10 hits
    window_pct: Optional[float] = None

    def __post_init__(self) -> None:
        if self.window_dollar is None and self.window_pct is None:
            raise ValueError(
                "RoundNumberSource requires window_dollar or window_pct"
            )
        if self.window_dollar is not None and self.window_dollar < 0:
            raise ValueError("window_dollar must be >= 0")
        if self.window_pct is not None and self.window_pct < 0:
            raise ValueError("window_pct must be >= 0")
        # Validate tier increments are positive numbers
        for tier, incs in self.increments.items():
            if tier not in TIER_BOUNDS:
                raise ValueError(
                    f"Unknown tier '{tier}'. Valid: {sorted(TIER_BOUNDS.keys())}"
                )
            if not incs:
                raise ValueError(f"tier '{tier}' has no increments")
            for inc in incs:
                if inc <= 0:
                    raise ValueError(
                        f"increment {inc} for tier '{tier}' must be > 0"
                    )

    # ----- LevelSourceProtocol -----

    def compute_levels(
        self,
        symbol: str,
        history: BarHistory,
    ) -> LevelSet:
        """Return all round-number levels in the proximity window of the
        latest bar close.

        If history is empty, returns an empty LevelSet (the strategy will
        retry once a bar arrives).
        """
        last = history.last
        if last is None:
            return LevelSet(symbol=symbol, session_date=self._inferred_date(history))
        return self._compute_for_price(
            symbol=symbol,
            current_price=float(last.close),
            session_date=self._inferred_date(history),
        )

    def update_intraday(self, bar: Bar) -> None:
        """Round numbers don't develop intraday — the level set is fully
        defined by the price tier and the configured window.
        """
        # No-op by design. update_intraday is part of the protocol so
        # orchestrators can call it uniformly across plugins.
        return None

    # ----- helpers exposed for backtests / cross-strategy code -----

    def levels_for_price(
        self,
        symbol: str,
        current_price: float,
        session_date: Optional[_date] = None,
    ) -> LevelSet:
        """Convenience: compute levels given only a price + optional date.

        Used by backtests that want to evaluate "what levels existed at
        moment X" without instantiating a BarHistory.
        """
        return self._compute_for_price(
            symbol=symbol,
            current_price=float(current_price),
            session_date=session_date or _date.today(),
        )

    # ----- internals -----

    def _inferred_date(self, history: BarHistory) -> _date:
        last = history.last
        if last is None or last.timestamp is None:
            return _date.today()
        try:
            return last.timestamp.date()
        except AttributeError:
            return _date.today()

    def _window_size(self, current_price: float) -> float:
        candidates: list[float] = []
        if self.window_dollar is not None:
            candidates.append(float(self.window_dollar))
        if self.window_pct is not None:
            candidates.append(float(current_price) * float(self.window_pct))
        return max(candidates) if candidates else 0.0

    def _compute_for_price(
        self,
        symbol: str,
        current_price: float,
        session_date: _date,
    ) -> LevelSet:
        tier = resolve_tier(current_price)
        if tier is None:
            return LevelSet(symbol=symbol, session_date=session_date)
        tier_increments = self.increments.get(tier, [])
        if not tier_increments:
            return LevelSet(symbol=symbol, session_date=session_date)

        window = self._window_size(current_price)
        if window <= 0:
            return LevelSet(symbol=symbol, session_date=session_date)

        lo = current_price - window
        hi = current_price + window

        # Build candidate levels for every configured increment in [lo, hi],
        # deduping where a single price (e.g. $50) is emitted by both
        # increments (1.00 and 5.00 both hit $50). The smaller increment
        # wins the metadata since it's the "tightest" structural anchor.
        seen: dict[float, Level] = {}
        # Sort increments asc so smallest wins on duplicate prices.
        for inc in sorted(tier_increments):
            # First multiple >= lo
            start_mult = int(lo // inc)
            # Walk up multiples until past hi
            k = start_mult
            while True:
                p = round(k * inc, 4)
                if p > hi + 1e-9:
                    break
                if p >= lo - 1e-9 and p > 0:
                    rounded_key = round(p, 4)
                    if rounded_key not in seen:
                        seen[rounded_key] = Level(
                            price=rounded_key,
                            kind="ROUND",
                            session_date=session_date,
                            metadata={
                                "tier": tier,
                                "increment": inc,
                                "ref_price": round(float(current_price), 4),
                            },
                        )
                k += 1

        # Order by price ascending — gives strategies a predictable
        # iteration order and aligns with ArrivalDetector picking the
        # first-in-order level when multiple are within proximity.
        ordered = tuple(sorted(seen.values(), key=lambda lv: lv.price))
        return LevelSet(symbol=symbol, session_date=session_date, levels=ordered)


# ---------------------------------------------------------------------------
# Module-level helpers — handy for the registry / strategy YAML loader.
# ---------------------------------------------------------------------------


def from_config(params: dict) -> RoundNumberSource:
    """Build a RoundNumberSource from a YAML `level_source.params` dict.

    Accepts:
        increments: dict[str, list[float]]   (optional, uses DEFAULT_INCREMENTS)
        window_dollar: float                  (default 5.0 if neither set)
        window_pct: float                     (optional)

    Unknown params are ignored (forward-compat for future knobs).
    """
    incs = params.get("increments")
    if incs is None:
        increments = {k: list(v) for k, v in DEFAULT_INCREMENTS.items()}
    else:
        increments = {k: [float(x) for x in v] for k, v in incs.items()}

    window_dollar = params.get("window_dollar")
    window_pct = params.get("window_pct")
    if window_dollar is None and window_pct is None:
        # Sensible default: ±$5 window covers all three tiers' increments.
        window_dollar = 5.0
    return RoundNumberSource(
        increments=increments,
        window_dollar=float(window_dollar) if window_dollar is not None else None,
        window_pct=float(window_pct) if window_pct is not None else None,
    )
