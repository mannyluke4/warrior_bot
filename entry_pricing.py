"""Shared entry-limit pricing for squeeze setups.

Used by both bot_v3_hybrid.py (live) and simulate.py (sim) so live and
backtest produce identical entry prices and dollar-risk math.

Background — see cowork_reports/2026-04-14_directive_limit_reprice_on_stale_arm.md.

The legacy formula `limit = trigger_high + 0.02` produces un-fillable orders
when current price is meaningfully above trigger (e.g. SKYQ 2026-04-13 trigger
$16.02 / market $17.35; ROLR 2026-04-14 trigger $7.02 / market $7.18). When
the arm is shallow-stale, this module re-prices the limit to current market
plus a configurable pad. Deeply-stale arms are refused (already filtered by
the WB_SQ_SEED_STALE_GATE in practice; this is belt-and-suspenders).

When the limit is re-priced, dollar-risk-based sizing must use
effective_R = limit - stop_low instead of the arm's original R, otherwise
position sizing oversizes the entry. compute_entry_limit() returns both
values so callers can route through the right R.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

DEFAULT_SLIPPAGE = 0.02


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _b(name: str, default: str = "1") -> bool:
    return os.getenv(name, default) == "1"


def compute_entry_limit(
    trigger_high: float,
    current_price: float,
    stop_low: float,
) -> Tuple[Optional[float], Optional[float], str]:
    """Return (limit_price, effective_R, tag).

    limit_price is None when the entry should be refused (deeply stale).
    effective_R is `limit - stop_low` ONLY when re-priced. For non-repriced
    paths it is None — caller MUST keep the arm's original R unchanged
    (otherwise the $0.02 difference between trigger-based R and the
    detector's entry_price-based R compounds across cascading entries
    and decimates baselines).
    tag is one of:
      - "legacy"           — feature disabled
      - "not_stale"        — current price <= trigger * (1 + MIN_PCT/100)
      - "repriced_stale_X.Xpct"
      - "refused_too_stale" / "refused_inverted_R"
    """
    legacy_limit = round(trigger_high + DEFAULT_SLIPPAGE, 2)

    enabled = _b("WB_STALE_ARM_REPRICE_ENABLED", "1")
    if not enabled:
        return legacy_limit, None, "legacy"

    if trigger_high <= 0 or current_price <= 0:
        return legacy_limit, None, "legacy"

    min_pct = _f("WB_STALE_ARM_REPRICE_MIN_PCT", 0.5)
    max_pct = _f("WB_STALE_ARM_REPRICE_MAX_PCT", 3.0)
    pad = _f("WB_STALE_ARM_REPRICE_PAD", 0.02)

    stale_ratio = (current_price - trigger_high) / trigger_high
    pct = stale_ratio * 100

    # Not stale (or below trigger) — use legacy
    if stale_ratio <= min_pct / 100.0:
        return legacy_limit, None, "not_stale"

    # Deeply stale — refuse. Stale-seed gate at 2.0% catches this in
    # practice; this is the belt-and-suspenders.
    if stale_ratio > max_pct / 100.0:
        return None, None, "refused_too_stale"

    # Shallow-stale — re-price to current market + pad.
    repriced = round(current_price + pad, 2)
    effective_R = repriced - stop_low
    if effective_R <= 0:
        return None, None, "refused_inverted_R"

    return repriced, effective_R, f"repriced_stale_{pct:.1f}pct"
