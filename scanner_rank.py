"""Unified scanner composite ranking (V1 + gated V2).

V1 (default): RVOL 40% / PM-vol 30% / gap 20% / float 10%, float capped at 10M.
The historical formula — kept as default so nothing changes without opting in.

V2 (WB_SCANNER_RANK_V2=1): float-forward. Built from the full-YTD stock-filter
study (2026-06-20, stock_filter_ytd.py over 115 cached days / 1,418 stock-days):
  - P(clean tradeable day) by float: <10M = 2.0x base, 10-50M = 1.7x, >=50M = 0.4x.
    Positive in every month Jan-Jun. Float is the single strongest selector.
  - Price: <$3 = 1.8x, >=$10 = 0.6x.
  - RVOL: 1.1x — does NOT discriminate (everything that shows up is already high-RVOL).
So V2 makes float the dominant weight, uncaps it to 50M (V1 zeroed everything >10M,
blind to the 1.7x 10-50M band), adds a price preference, and demotes RVOL to a minor
liquidity nudge. Gap + PM-vol retained so the scanner still surfaces real movers.

Gated OFF by default per the project no-regression rule. Flip WB_SCANNER_RANK_V2=1
to enable; backtest ordering against the clean-day labels before going live.
"""
import os
import math


def _v1(rvol: float, pm_vol: float, gap: float, float_m: float) -> float:
    rvol_score = math.log10(min(rvol, 50) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap, 100) / 100
    float_score = 1 - (min(float_m, 10) / 10)
    return (0.40 * rvol_score) + (0.30 * vol_score) + (0.20 * gap_score) + (0.10 * float_score)


def _v2(rvol: float, pm_vol: float, gap: float, float_m: float, price) -> float:
    rvol_score = math.log10(min(rvol, 50) + 1) / math.log10(51)
    vol_score = math.log10(max(pm_vol, 1)) / 8
    gap_score = min(gap, 100) / 100
    # float: reward across the proven 0-50M band, zero above (>=50M = 0.4x = junk).
    float_score = max(0.0, 1 - (min(float_m, 50) / 50))
    # price: cheaper is better; >=$10 (0.6x) gets nothing. Neutral 0.5 if unknown.
    price_score = 0.5 if not price else max(0.0, 1 - (min(price, 10) / 10))
    return ((0.40 * float_score) + (0.20 * gap_score) + (0.15 * vol_score)
            + (0.15 * price_score) + (0.10 * rvol_score))


def composite_rank(rvol=0.0, pm_vol=0.0, gap=0.0, float_m=10.0, price=None) -> float:
    """Dispatch V1/V2 by WB_SCANNER_RANK_V2. All args defaulted/None-safe."""
    rvol = rvol or 0.0
    pm_vol = pm_vol or 0.0
    gap = gap or 0.0
    float_m = float_m or 10.0
    if os.getenv("WB_SCANNER_RANK_V2", "0") == "1":
        return _v2(rvol, pm_vol, gap, float_m, price)
    return _v1(rvol, pm_vol, gap, float_m)
