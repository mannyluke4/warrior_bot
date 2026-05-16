"""Synthetic L2 generator — Wave 5 Agent N.

L2 (market depth / order-book) historical data is NOT in our Databento
Standard subscription.  Per the Agent N directive, this module produces
a *proxy* L2 state from existing 1-minute bar data so the L2 confirmation
plugin can be exercised end-to-end on the 36-symbol shortlist.

The synthetic state is shaped to satisfy
``framework.confirmations.l2_confirm.L2Confirm``'s ``depth_imbalance``
input contract — a dict with ``bids`` / ``asks`` lists of (price, size)
tuples — so the same plugin code runs on synthetic and real L2.

Heuristics (all justified by tape-reading literature; see report §3.1)
=====================================================================

For each 1m bar at level-touch time:

* **Depth imbalance proxy — wick asymmetry.**
  - A bar with a long upper wick (relative to body + lower wick) signals
    *ask absorption* — institutional selling capped the move.  Reading
    that as L2: bigger asks above price, thinner bids below ->
    BEARISH imbalance.
  - A long lower wick signals *bid absorption* -> BULLISH imbalance.
  - We map wick-asymmetry s ∈ [-1, 1] to a bid/ask size ratio in
    [1/3, 3].

* **Top-of-book size — bar volume scaled.**
  Top-level size ≈ vol_share × bar_volume, where vol_share defaults to
  5% (the institutional fill model's bar-volume cap).  Levels below
  taper geometrically.

* **Momentum vacuum proxy — volume delta.**
  ``opposite_side_drop_pct = max(0, 1 - cur_vol / prior_vol)`` when
  bar volume drops vs the prior bar in the direction of the wick (the
  fading side is "vacuuming").

This is NOT real L2.  The output is plausible directional structure
that the plugin can act on; absolute fill numbers are not credible.

Production capture spec
-----------------------

When live L2 capture lands (see ``docs/l2_capture_spec.md``), replace
this generator with a parquet reader over ``l2_cache/`` and the same
plugin runs unchanged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from framework.level_sources.base import Bar


# ---------------------------------------------------------------------------
# Wick / volume helpers
# ---------------------------------------------------------------------------


def wick_skew(bar: Bar) -> float:
    """Wick-asymmetry score in [-1, +1].

    Positive => upper wick dominates => bearish imbalance (ask absorption).
    Negative => lower wick dominates => bullish imbalance (bid absorption).
    Zero => symmetric.
    """
    upper = bar.upper_wick
    lower = bar.lower_wick
    total = upper + lower
    if total <= 0:
        return 0.0
    return (upper - lower) / total


def _safe_close(bar: Bar) -> float:
    return float(bar.close) if math.isfinite(bar.close) and bar.close > 0 else 0.0


# ---------------------------------------------------------------------------
# Top-of-book proxy
# ---------------------------------------------------------------------------


@dataclass
class SyntheticL2Config:
    """Knobs for the synthetic generator (calibrated to fill-model research)."""

    levels: int = 5                # top-N levels per side
    vol_share: float = 0.05         # 5% of bar volume on top level
    taper: float = 0.6              # each next level = taper × prior level
    tick_size: float = 0.01         # price increment between levels
    # Wick-skew -> ratio mapping.  At |skew|=1, ratio = max_ratio.
    max_ratio: float = 3.0
    min_ratio: float = 1.0 / 3.0


def synth_l2_state(
    bar: Bar,
    *,
    prior_bar: Optional[Bar] = None,
    config: Optional[SyntheticL2Config] = None,
) -> dict[str, Any]:
    """Build a synthetic L2 state dict from a 1-minute bar.

    Returns the dict shape ``L2Confirm(mode='depth_imbalance')`` and the
    ``momentum_vacuum`` aggregated path consume.
    """
    cfg = config or SyntheticL2Config()
    price = _safe_close(bar)
    if price <= 0 or not math.isfinite(bar.volume) or bar.volume <= 0:
        return {
            "bids": [],
            "asks": [],
            "timestamp": bar.timestamp,
            "opposite_side_drop_pct": 0.0,
        }

    skew = wick_skew(bar)
    # Map skew in [-1, 1] -> ratio in [min_ratio, max_ratio] via log-linear.
    # skew=-1 -> max ratio (bullish: bid much greater than ask)
    # skew=+1 -> min ratio (bearish: bid << ask)
    log_min = math.log(cfg.min_ratio)
    log_max = math.log(cfg.max_ratio)
    # skew=-1 → log_max ; skew=+1 → log_min  → slope = -(log_max-log_min)/2
    log_ratio = (log_max + log_min) / 2 - skew * (log_max - log_min) / 2
    ratio = math.exp(log_ratio)  # bid_total / ask_total

    base_size = max(1.0, cfg.vol_share * bar.volume)

    # Distribute base across N levels with geometric taper.
    weights = [cfg.taper ** i for i in range(cfg.levels)]
    weight_sum = sum(weights)
    # bid_total / ask_total = ratio, total = base_size + base_size = 2*base_size
    # Allocate by ratio: bid_total = base*(ratio/(ratio+1))*2, ask_total = base*(1/(ratio+1))*2
    bid_total = 2 * base_size * ratio / (ratio + 1.0)
    ask_total = 2 * base_size * 1.0 / (ratio + 1.0)

    bids: list[tuple[float, float]] = []
    asks: list[tuple[float, float]] = []
    for i, w in enumerate(weights):
        bp = price - cfg.tick_size * (i + 1)
        ap = price + cfg.tick_size * (i + 1)
        b_size = round(bid_total * w / weight_sum, 0)
        a_size = round(ask_total * w / weight_sum, 0)
        bids.append((bp, b_size))
        asks.append((ap, a_size))

    state: dict[str, Any] = {
        "bids": bids,
        "asks": asks,
        "timestamp": bar.timestamp,
    }

    # Momentum vacuum proxy: opposite-side drop when current bar volume is
    # markedly smaller than prior bar AND skew favors a particular side.
    if prior_bar is not None and math.isfinite(prior_bar.volume) and prior_bar.volume > 0:
        vol_delta = (prior_bar.volume - bar.volume) / prior_bar.volume
        # Direction-blind here: the consumer infers direction from the
        # level kind via L2Confirm.  We just expose the magnitude.
        state["opposite_side_drop_pct"] = max(0.0, vol_delta)
    else:
        state["opposite_side_drop_pct"] = 0.0

    # Aggregated keys the legacy mode looks for (so callers can swap modes).
    bid_total_actual = sum(s for _, s in bids)
    ask_total_actual = sum(s for _, s in asks)
    if bid_total_actual + ask_total_actual > 0:
        state["imbalance"] = bid_total_actual / (bid_total_actual + ask_total_actual)
    else:
        state["imbalance"] = 0.5
    state["spread_pct"] = (cfg.tick_size / price) * 100.0
    state["bid_stacking"] = bid_total_actual >= ask_total_actual * 2.0
    state["bid_stack_levels"] = (
        [(p, s) for p, s in bids if s >= 0.5 * base_size]
        if state["bid_stacking"]
        else []
    )
    state["large_bid"] = False
    state["large_ask"] = False
    state["ask_thinning"] = ask_total_actual < bid_total_actual * 0.5

    return state


# ---------------------------------------------------------------------------
# Batch helper — synthesize over a bar series
# ---------------------------------------------------------------------------


def synth_series(bars: list[Bar], config: Optional[SyntheticL2Config] = None) -> list[dict[str, Any]]:
    """Return a list of synthetic L2 states for each bar, with prior context."""
    states: list[dict[str, Any]] = []
    prev: Optional[Bar] = None
    for b in bars:
        states.append(synth_l2_state(b, prior_bar=prev, config=config))
        prev = b
    return states
