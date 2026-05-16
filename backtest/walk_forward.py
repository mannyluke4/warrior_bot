"""Wave 3 Agent K — Walk-forward / robustness validation harness.

This is a self-contained bar-level harness that runs the five Wave 2 strategies
(ORB-5min, VWAP-MeanRev, PDH-Fade, PDH-Breakout, RoundNumber-$50-150) over the
2020-01 → 2024-12 window using a regime-rich synthetic data generator.

We fall back to synthetic data per Wave 2 synthesis: Agent J's subprocess
Nautilus runner is not yet shipped, and Databento bulk-pulls exceed the standard
plan budget for arbitrary universes. Per directive, we make the regime
classifier richer by switching macro regimes every 90 days (quarterly) so the
synthetic series exposes the strategies to a calibrated mix of bull/bear/chop
× high-vol/low-vol windows.

Output:
  - per-test-month metrics (Sharpe, trades, MaxDD)
  - 50 train/test windows × 5 strategies = 250 walk-forward cells
  - per-quarter P&L breakdown for concentration check
  - regime sub-tests (bull/bear/chop × high/med/low VIX = 9 cells)
  - parameter sensitivity sweeps (5 points × ±20% range per parameter)
  - block bootstrap of daily P&L (1000 samples, 20-day blocks)

The harness is deliberately fast: ~10 symbols × 1260 trading days × 5 strategies
runs in a few minutes on a laptop, so the full robustness sweep completes in a
single session.

Per directive §4 Agent K:
  - Walk-forward Sharpe positive in ≥70% of test months
  - Sharpe stays > 1.0 within ±20% on every key parameter
  - Single-quarter concentration ≤ 40%
  - Bootstrap Sharpe lower-95%-CI > 0

Strategy interpretability is limited by synthetic data — particularly for
trend-following strategies (GBM has no real trend autocorrelation). The intent
is to expose framework-level robustness/sensitivity behavior; absolute Sharpe
numbers should be interpreted as comparative across strategies on the SAME
underlying data, not as deployable edge estimates.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.level_sources.base import Bar, BarHistory, Level, LevelSet


# =============================================================================
# REGIME-RICH SYNTHETIC GENERATOR
# =============================================================================


@dataclass
class MacroRegime:
    """One 90-day macro regime block. Used to vary trend + vol every quarter."""

    name: str             # "bull_lowvol", "bear_highvol", "chop_medvol", etc.
    trend: float          # daily drift in % terms (e.g. +0.0010 = +0.1%/day)
    vol_pct: float        # daily vol in % terms (e.g. 0.025 = 2.5%/day)
    spy_drift: float      # SPY's daily drift this quarter (for regime classifier)
    vix_level: float      # average VIX this quarter (for vol classifier)
    reaction_prob: float  # prob session "reacts" at a level (40-60% normally)
    breakout_prob: float  # prob non-reaction session "breaks" the level


# Regime menu — 8 distinct macros, drawn in a rotation to give 20 quarters
# over 5 years a balanced mix of bull / bear / chop and high / med / low vol.
REGIME_MENU: list[MacroRegime] = [
    MacroRegime("bull_lowvol",  +0.0012, 0.015, +0.0012, 14.0, 0.45, 0.65),
    MacroRegime("bull_medvol",  +0.0010, 0.022, +0.0010, 20.0, 0.45, 0.65),
    MacroRegime("bull_highvol", +0.0008, 0.035, +0.0008, 28.0, 0.40, 0.60),
    MacroRegime("chop_lowvol",   0.0000, 0.012,  0.0000, 13.0, 0.55, 0.45),
    MacroRegime("chop_medvol",   0.0000, 0.020,  0.0000, 19.0, 0.55, 0.45),
    MacroRegime("chop_highvol",  0.0000, 0.032,  0.0000, 27.0, 0.50, 0.40),
    MacroRegime("bear_medvol",  -0.0008, 0.024, -0.0008, 24.0, 0.50, 0.55),
    MacroRegime("bear_highvol", -0.0012, 0.038, -0.0012, 32.0, 0.45, 0.55),
]


def regime_for_quarter(q_idx: int) -> MacroRegime:
    """Deterministic regime assignment per quarter, weighted toward chop+med."""
    # Sequence designed to give a realistic ~25% bull, ~20% bear, ~55% chop mix
    # across 20 quarters (5 years × 4), with vol regimes interleaved.
    seq = [
        "bull_medvol", "bull_lowvol",   "chop_medvol",  "chop_highvol",  # 2020 (covid)
        "bull_highvol", "bull_medvol",  "chop_lowvol",  "chop_medvol",   # 2021
        "bear_highvol", "bear_medvol",  "chop_highvol", "bear_medvol",   # 2022
        "chop_medvol",  "bull_medvol",  "chop_lowvol",  "bull_lowvol",   # 2023
        "bull_medvol",  "chop_medvol",  "bull_lowvol",  "chop_medvol",   # 2024
    ]
    name = seq[q_idx % len(seq)]
    for r in REGIME_MENU:
        if r.name == name:
            return r
    return REGIME_MENU[0]


def _trading_days(start: date, end: date) -> list[date]:
    out = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            # Approximate US market holidays
            if not ((cur.month, cur.day) in {(1, 1), (7, 4), (12, 25)}):
                out.append(cur)
        cur += timedelta(days=1)
    return out


def _quarter_index(d: date, start: date) -> int:
    """0-indexed quarter offset from start date."""
    months = (d.year - start.year) * 12 + (d.month - start.month)
    return months // 3


def generate_regime_bars(
    symbol: str,
    sym_seed: int,
    base_price: float,
    start_date: date,
    end_date: date,
    bar_minutes: int = 5,
) -> tuple[dict[tuple[str, date], list[Bar]], pd.DataFrame]:
    """Generate full (symbol, date) -> [Bar] map with quarterly regime shifts.

    Also returns a per-day regime + SPY-proxy DataFrame for regime classification.

    Each session has 78 5-min RTH bars (09:30-16:00). Within a session, drift
    follows the active macro regime; reaction/breakout probabilities at the
    prior session's high/low are tuned per regime so PDH/PDL strategies see
    realistic edge variation.
    """
    bars_map: dict[tuple[str, date], list[Bar]] = {}
    days = _trading_days(start_date, end_date)

    rng = np.random.default_rng(sym_seed)
    price = base_price
    prior_high: Optional[float] = None
    prior_low: Optional[float] = None
    regime_log: list[dict] = []

    rth_open = time(9, 30)
    rth_close = time(16, 0)
    total_minutes = (rth_close.hour - rth_open.hour) * 60
    n_bars = total_minutes // bar_minutes

    for d in days:
        q_idx = _quarter_index(d, start_date)
        regime = regime_for_quarter(q_idx)

        # Overnight gap (regime-shaped)
        gap = rng.normal(regime.trend, regime.vol_pct * 0.4)
        open_price = max(0.5, price * (1.0 + gap))

        # Session-level drift + vol drawn from regime
        daily_drift = regime.trend
        daily_vol = regime.vol_pct
        bar_sigma = open_price * daily_vol / math.sqrt(n_bars)
        drift_per_bar = daily_drift * open_price / n_bars

        # Decide reaction plan if we have a prior level
        plan: Optional[tuple[str, str, float]] = None
        if prior_high is not None and prior_low is not None:
            u = rng.random()
            # PDH if open closer to PDH, PDL otherwise
            if abs(open_price - prior_high) < abs(open_price - prior_low):
                target_level = prior_high
                level_side = "PDH"
            else:
                target_level = prior_low
                level_side = "PDL"
            if u < regime.reaction_prob:
                plan = ("react", level_side, target_level)
            elif u < regime.reaction_prob + (1 - regime.reaction_prob) * regime.breakout_prob:
                plan = ("break", level_side, target_level)
            else:
                plan = ("ignore", level_side, target_level)

        touch_idx = int(rng.integers(low=4, high=max(5, n_bars - 8)))

        bars: list[Bar] = []
        cur_price = open_price
        session_high = open_price
        session_low = open_price
        base_volume = rng.uniform(5000, 30000)
        has_spiked = False
        # Adjust drift mid-session after reaction/break
        active_drift = drift_per_bar

        # Compute opening 5-min direction (regime-dependent)
        # ORB direction-bias bar will be the very first bar — we want its color
        # to lean with regime trend on average so direction-bias signals are
        # not random.
        opening_drift_bias = regime.trend * open_price * 0.5  # half of daily drift in 5 min
        for i in range(n_bars):
            minutes_from_open = i * bar_minutes
            ts = datetime.combine(d, rth_open) + timedelta(minutes=minutes_from_open)

            if plan is not None and plan[0] in ("react", "break") and i == touch_idx:
                target_level = plan[2]
                if plan[1] == "PDH":
                    target_high = target_level * (1.0 + rng.uniform(0.0005, 0.003))
                    target_low = cur_price * (1.0 - rng.uniform(0.0005, 0.002))
                    if plan[0] == "react":
                        new_close = target_level * (1.0 - rng.uniform(0.0008, 0.004))
                    else:
                        new_close = target_level * (1.0 + rng.uniform(0.0015, 0.005))
                    bar_open = cur_price
                    bar_high = max(target_high, bar_open, new_close)
                    bar_low = min(target_low, bar_open, new_close)
                    vol_mult = rng.uniform(2.5, 4.0)
                else:  # PDL
                    target_low = target_level * (1.0 - rng.uniform(0.0005, 0.003))
                    target_high = cur_price * (1.0 + rng.uniform(0.0005, 0.002))
                    if plan[0] == "react":
                        new_close = target_level * (1.0 + rng.uniform(0.0008, 0.004))
                    else:
                        new_close = target_level * (1.0 - rng.uniform(0.0015, 0.005))
                    bar_open = cur_price
                    bar_low = min(target_low, bar_open, new_close)
                    bar_high = max(target_high, bar_open, new_close)
                    vol_mult = rng.uniform(2.5, 4.0)
                bar_close = new_close
                cur_price = new_close
                # Step drift to follow-through after the event
                if plan[0] == "react":
                    if plan[1] == "PDH":
                        active_drift = -abs(drift_per_bar) - open_price * 0.0008
                    else:
                        active_drift = abs(drift_per_bar) + open_price * 0.0008
                else:
                    if plan[1] == "PDH":
                        active_drift = abs(drift_per_bar) + open_price * 0.0012
                    else:
                        active_drift = -abs(drift_per_bar) - open_price * 0.0012
            else:
                bar_open = cur_price
                # Add opening-bar bias for ORB direction
                local_drift = active_drift
                if i == 0:
                    local_drift = active_drift + opening_drift_bias
                eps = rng.normal(0, bar_sigma)
                bar_close = max(0.01, bar_open + local_drift + eps)
                wick_lo = abs(rng.normal(0, bar_sigma * 0.5))
                wick_hi = abs(rng.normal(0, bar_sigma * 0.5))
                bar_high = max(bar_open, bar_close) + wick_hi
                bar_low = min(bar_open, bar_close) - wick_lo
                bar_low = max(0.01, bar_low)
                cur_price = bar_close
                t_norm = i / max(1, n_bars - 1)
                u_shape = 1.0 + 1.0 * (1.0 - 4.0 * t_norm * (1.0 - t_norm))
                vol_mult = u_shape * rng.uniform(0.7, 1.3)
                if not has_spiked and rng.random() < 2.0 / n_bars:
                    vol_mult *= rng.uniform(2.0, 3.5)
                    has_spiked = True

            session_high = max(session_high, bar_high)
            session_low = min(session_low, bar_low)

            bars.append(Bar(
                timestamp=ts,
                open=round(bar_open, 4),
                high=round(bar_high, 4),
                low=round(bar_low, 4),
                close=round(bar_close, 4),
                volume=round(base_volume * vol_mult, 0),
                symbol=symbol,
            ))

        bars_map[(symbol, d)] = bars
        prior_high = session_high
        prior_low = session_low
        price = bars[-1].close

        # Log regime for classifier
        regime_log.append({
            "date": d,
            "regime_name": regime.name,
            "trend": regime.trend,
            "vix_proxy": regime.vix_level + rng.normal(0, 1.5),
            "spy_drift": regime.spy_drift,
        })

    regime_df = pd.DataFrame(regime_log)
    return bars_map, regime_df


# =============================================================================
# REGIME CLASSIFIER
# =============================================================================


def classify_regimes(regime_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each day with bull/bear/chop (via SPY-proxy rolling 3-month return)
    and high/med/low vol (via VIX-proxy quarterly average).
    """
    df = regime_df.copy().sort_values("date").reset_index(drop=True)
    # Synthetic SPY level from cumulative drift (simulated as if SPY tracks
    # quarterly trend)
    df["spy_level"] = (1 + df["spy_drift"]).cumprod() * 400.0
    df["spy_3mo_ret"] = df["spy_level"].pct_change(63)  # 63 trading days ≈ 3mo
    df["spy_3mo_ret"] = df["spy_3mo_ret"].fillna(0.0)
    # Quarterly average VIX
    df["quarter"] = df["date"].apply(lambda d: pd.Period(d, freq="Q"))
    df["vix_avg_q"] = df.groupby("quarter")["vix_proxy"].transform("mean")

    def market_label(r):
        if r > 0.05:
            return "bull"
        if r < -0.05:
            return "bear"
        return "chop"

    def vol_label(v):
        if v > 25:
            return "highvol"
        if v < 18:
            return "lowvol"
        return "medvol"

    df["market"] = df["spy_3mo_ret"].apply(market_label)
    df["volregime"] = df["vix_avg_q"].apply(vol_label)
    return df[["date", "market", "volregime", "spy_3mo_ret", "vix_avg_q"]]


# =============================================================================
# UNIVERSE
# =============================================================================


def make_universe(
    n_symbols: int,
    start_date: date,
    end_date: date,
    base_seed: int = 7,
) -> tuple[dict[tuple[str, date], list[Bar]], pd.DataFrame]:
    """Generate a multi-symbol universe across 2020-2024. Symbols have base
    prices log-uniform in [$15, $250] to cover all tiers.
    """
    rng = np.random.default_rng(base_seed)
    bars_all: dict[tuple[str, date], list[Bar]] = {}
    regime_df: Optional[pd.DataFrame] = None
    for s_idx in range(n_symbols):
        base = math.exp(rng.uniform(math.log(15), math.log(250)))
        sym = f"SYM{s_idx:02d}"
        bars_map, rdf = generate_regime_bars(
            symbol=sym,
            sym_seed=base_seed * 1000 + s_idx,
            base_price=round(base, 2),
            start_date=start_date,
            end_date=end_date,
        )
        bars_all.update(bars_map)
        if regime_df is None:
            regime_df = rdf
    return bars_all, regime_df


# =============================================================================
# STRATEGY SIMULATORS (compact, one-trade-per-symbol-per-day)
# =============================================================================


@dataclass
class StratParams:
    """All tunable parameters per strategy. ±20% sweeps apply to these."""

    # ORB
    orb_minutes: int = 5
    orb_vol_mult: float = 2.0
    orb_min_breakout_pct: float = 0.0002
    orb_proximity_pct: float = 0.001
    orb_r_multiple: float = 2.0

    # VWAP MeanRev
    vwap_band_sigma: float = 2.0
    vwap_proximity_pct: float = 0.003
    vwap_lookback_bars: int = 2
    vwap_stop_pad: float = 0.10
    vwap_r_multiple: float = 1.5

    # PDH Fade
    fade_proximity_pct: float = 0.001
    fade_lookback: int = 2
    fade_stop_pad: float = 0.10
    fade_r_multiple: float = 1.5

    # PDH Breakout
    brk_proximity_pct: float = 0.0005
    brk_vol_mult: float = 2.0
    brk_min_breakout_pct: float = 0.0002
    brk_stop_pad: float = 0.02
    brk_r_multiple: float = 2.0

    # Round Number ($50-150 tier — only this tier per directive)
    rn_increment: float = 5.0
    rn_proximity_dollar: float = 0.25
    rn_stop_pad: float = 0.10
    rn_r_multiple: float = 2.0


@dataclass
class TradeRec:
    """Lightweight trade record for metrics."""
    symbol: str
    session_date: date
    strategy: str
    pnl: float
    r: float
    direction: str


def _opening_range(bars: list[Bar], minutes: int) -> tuple[float, float, str]:
    """Return (orh, orl, direction_bias) from first `minutes` of session."""
    if not bars:
        return 0, 0, "neutral"
    end_dt = bars[0].timestamp + timedelta(minutes=minutes)
    window = [b for b in bars if b.timestamp < end_dt]
    if not window:
        return bars[0].high, bars[0].low, "neutral"
    orh = max(b.high for b in window)
    orl = min(b.low for b in window)
    bias = "long" if window[-1].close > window[0].open else "short"
    return orh, orl, bias


def _vol_baseline(bars: list[Bar], up_to_idx: int, window: int = 20) -> float:
    lo = max(0, up_to_idx - window)
    if lo == up_to_idx:
        return 0.0
    return float(np.mean([b.volume for b in bars[lo:up_to_idx]]))


def _running_vwap(bars: list[Bar], idx: int) -> tuple[float, float]:
    """Return (vwap, std_band_sigma) at bar idx (inclusive)."""
    pv = 0.0
    vol = 0.0
    typs: list[float] = []
    for j in range(idx + 1):
        b = bars[j]
        typ = (b.high + b.low + b.close) / 3.0
        pv += typ * b.volume
        vol += b.volume
        typs.append(typ)
    if vol == 0:
        return bars[idx].close, 0.0
    vwap = pv / vol
    if len(typs) < 2:
        return vwap, 0.0
    sigma = float(np.std(typs))
    return vwap, sigma


def _next_round_above(price: float, increment: float) -> float:
    return math.ceil(price / increment + 1e-9) * increment


def _next_round_below(price: float, increment: float) -> float:
    return math.floor(price / increment - 1e-9) * increment


def _is_doji(b: Bar) -> bool:
    rng = b.high - b.low
    if rng <= 0:
        return False
    return b.body / rng < 0.15


def _is_hammer(b: Bar) -> bool:
    rng = b.high - b.low
    if rng <= 0:
        return False
    return (b.lower_wick > 2 * b.body) and (b.upper_wick < b.body)


def _is_shooting_star(b: Bar) -> bool:
    rng = b.high - b.low
    if rng <= 0:
        return False
    return (b.upper_wick > 2 * b.body) and (b.lower_wick < b.body)


# ---- ORB ----


def simulate_orb(bars: list[Bar], cfg: StratParams, equity: float) -> Optional[TradeRec]:
    if len(bars) < cfg.orb_minutes + 5:
        return None
    orh, orl, bias = _opening_range(bars, cfg.orb_minutes)
    # Bars after the opening window
    window_end_dt = bars[0].timestamp + timedelta(minutes=cfg.orb_minutes)
    entry_idx = None
    direction = None
    entry_level = None
    for i in range(len(bars)):
        b = bars[i]
        if b.timestamp < window_end_dt:
            continue
        baseline = _vol_baseline(bars, i)
        if baseline <= 0:
            continue
        vol_mult = b.volume / baseline
        # Long break of ORH
        if bias == "long" and b.close > orh * (1 + cfg.orb_min_breakout_pct):
            if vol_mult >= cfg.orb_vol_mult:
                entry_idx = i
                direction = "long"
                entry_level = orh
                break
        if bias == "short" and b.close < orl * (1 - cfg.orb_min_breakout_pct):
            if vol_mult >= cfg.orb_vol_mult:
                entry_idx = i
                direction = "short"
                entry_level = orl
                break
    if entry_idx is None or entry_idx + 1 >= len(bars):
        return None
    fill = bars[entry_idx + 1]
    entry_price = fill.open
    stop = orl if direction == "long" else orh
    if direction == "long" and stop >= entry_price:
        return None
    if direction == "short" and stop <= entry_price:
        return None
    per_share_risk = abs(entry_price - stop)
    if per_share_risk <= 0:
        return None
    risk_dollars = equity * 0.01  # 1% per trade
    qty = int(risk_dollars / per_share_risk)
    if qty <= 0:
        return None
    target = (entry_price + cfg.orb_r_multiple * per_share_risk) if direction == "long" \
        else (entry_price - cfg.orb_r_multiple * per_share_risk)
    return _walk_exit(bars, entry_idx + 1, entry_price, stop, target, qty, direction,
                      symbol=bars[0].symbol, strategy="ORB-5min", risk_dollars=risk_dollars)


# ---- VWAP Mean-Reversion ----


def simulate_vwap_mr(bars: list[Bar], cfg: StratParams, equity: float) -> Optional[TradeRec]:
    if len(bars) < 10:
        return None
    # Only fire in "flat" regime — approximate by checking small slope of VWAP
    # over last 10 bars
    for i in range(10, len(bars) - 1):
        b = bars[i]
        vwap, sigma = _running_vwap(bars, i)
        upper_band = vwap + cfg.vwap_band_sigma * sigma
        lower_band = vwap - cfg.vwap_band_sigma * sigma
        # Slope check: VWAP should be roughly flat
        vwap_prev, _ = _running_vwap(bars, max(0, i - 10))
        slope = (vwap - vwap_prev) / max(vwap_prev, 1e-9)
        if abs(slope) > 0.002:  # >0.2% over 10 bars = trending, skip
            continue
        # Check if recent bar touched a band and closed back inside (rejection)
        for j in range(max(0, i - cfg.vwap_lookback_bars), i + 1):
            bj = bars[j]
            # Upper band touch (short setup)
            if bj.high >= upper_band and b.close < upper_band:
                # Rejection from above — short
                entry_idx = i + 1
                if entry_idx >= len(bars):
                    return None
                entry_price = bars[entry_idx].open
                stop = upper_band + cfg.vwap_stop_pad
                target = vwap  # opposite_level = VWAP center
                if stop <= entry_price:
                    continue
                per_share_risk = abs(entry_price - stop)
                if per_share_risk <= 0:
                    continue
                risk_dollars = equity * 0.01
                qty = int(risk_dollars / per_share_risk)
                if qty <= 0:
                    continue
                return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "short",
                                  symbol=bars[0].symbol, strategy="VWAP-MeanRev",
                                  risk_dollars=risk_dollars)
            # Lower band touch (long setup)
            if bj.low <= lower_band and b.close > lower_band:
                entry_idx = i + 1
                if entry_idx >= len(bars):
                    return None
                entry_price = bars[entry_idx].open
                stop = lower_band - cfg.vwap_stop_pad
                target = vwap
                if stop >= entry_price:
                    continue
                per_share_risk = abs(entry_price - stop)
                if per_share_risk <= 0:
                    continue
                risk_dollars = equity * 0.01
                qty = int(risk_dollars / per_share_risk)
                if qty <= 0:
                    continue
                return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "long",
                                  symbol=bars[0].symbol, strategy="VWAP-MeanRev",
                                  risk_dollars=risk_dollars)
    return None


# ---- PDH/PDL Fade ----


def simulate_pdh_fade(
    bars: list[Bar], pdh: float, pdl: float, cfg: StratParams, equity: float
) -> Optional[TradeRec]:
    if len(bars) < 5:
        return None
    for i in range(2, len(bars) - 1):
        b = bars[i]
        threshold = b.close * cfg.fade_proximity_pct
        # PDH rejection — short
        if b.high >= pdh - threshold and b.close < pdh:
            # Look back lookback_bars to confirm rejection pattern
            recent_touched = any(bars[j].high >= pdh for j in range(max(0, i - cfg.fade_lookback), i + 1))
            if recent_touched:
                entry_idx = i + 1
                entry_price = bars[entry_idx].open
                stop = pdh + cfg.fade_stop_pad
                target = pdl
                if stop <= entry_price:
                    continue
                per_share_risk = abs(entry_price - stop)
                if per_share_risk <= 0:
                    continue
                risk_dollars = equity * 0.01
                qty = int(risk_dollars / per_share_risk)
                if qty <= 0:
                    continue
                return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "short",
                                  symbol=bars[0].symbol, strategy="PDH-Fade",
                                  risk_dollars=risk_dollars)
        # PDL rejection — long
        if b.low <= pdl + threshold and b.close > pdl:
            recent_touched = any(bars[j].low <= pdl for j in range(max(0, i - cfg.fade_lookback), i + 1))
            if recent_touched:
                entry_idx = i + 1
                entry_price = bars[entry_idx].open
                stop = pdl - cfg.fade_stop_pad
                target = pdh
                if stop >= entry_price:
                    continue
                per_share_risk = abs(entry_price - stop)
                if per_share_risk <= 0:
                    continue
                risk_dollars = equity * 0.01
                qty = int(risk_dollars / per_share_risk)
                if qty <= 0:
                    continue
                return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "long",
                                  symbol=bars[0].symbol, strategy="PDH-Fade",
                                  risk_dollars=risk_dollars)
    return None


# ---- PDH/PDL Breakout ----


def simulate_pdh_break(
    bars: list[Bar], pdh: float, pdl: float, cfg: StratParams, equity: float
) -> Optional[TradeRec]:
    if len(bars) < 5:
        return None
    for i in range(2, len(bars) - 1):
        b = bars[i]
        baseline = _vol_baseline(bars, i)
        if baseline <= 0:
            continue
        vol_mult = b.volume / baseline
        if vol_mult < cfg.brk_vol_mult:
            continue
        # Long break of PDH
        if b.close > pdh * (1 + cfg.brk_min_breakout_pct):
            entry_idx = i + 1
            if entry_idx >= len(bars):
                return None
            entry_price = bars[entry_idx].open
            stop = bars[i].low - cfg.brk_stop_pad
            if stop >= entry_price:
                continue
            per_share_risk = abs(entry_price - stop)
            if per_share_risk <= 0:
                continue
            target = entry_price + cfg.brk_r_multiple * per_share_risk
            risk_dollars = equity * 0.01
            qty = int(risk_dollars / per_share_risk)
            if qty <= 0:
                continue
            return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "long",
                              symbol=bars[0].symbol, strategy="PDH-Breakout",
                              risk_dollars=risk_dollars)
        # Short break of PDL
        if b.close < pdl * (1 - cfg.brk_min_breakout_pct):
            entry_idx = i + 1
            if entry_idx >= len(bars):
                return None
            entry_price = bars[entry_idx].open
            stop = bars[i].high + cfg.brk_stop_pad
            if stop <= entry_price:
                continue
            per_share_risk = abs(entry_price - stop)
            if per_share_risk <= 0:
                continue
            target = entry_price - cfg.brk_r_multiple * per_share_risk
            risk_dollars = equity * 0.01
            qty = int(risk_dollars / per_share_risk)
            if qty <= 0:
                continue
            return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "short",
                              symbol=bars[0].symbol, strategy="PDH-Breakout",
                              risk_dollars=risk_dollars)
    return None


# ---- Round Number $50-150 ----


def simulate_round_number(bars: list[Bar], cfg: StratParams, equity: float) -> Optional[TradeRec]:
    if len(bars) < 5:
        return None
    # Only fires on $50-150 tier symbols
    if not (50 <= bars[0].close <= 150):
        return None
    for i in range(3, len(bars) - 1):
        b = bars[i]
        # Find nearest round number above/below current price
        above = _next_round_above(b.close, cfg.rn_increment)
        below = _next_round_below(b.close, cfg.rn_increment)
        # Test arrival at resistance (above)
        if abs(b.high - above) <= cfg.rn_proximity_dollar and b.close < above:
            # Need signal candle + volume increase
            if _is_doji(b) or _is_shooting_star(b):
                prev_vol = bars[i - 1].volume if i > 0 else 0
                if b.volume > prev_vol:
                    # Short setup, target = below
                    entry_idx = i + 1
                    entry_price = bars[entry_idx].open
                    stop = above + cfg.rn_stop_pad
                    target = below
                    if stop <= entry_price or target >= entry_price:
                        continue
                    per_share_risk = abs(entry_price - stop)
                    if per_share_risk <= 0:
                        continue
                    risk_dollars = equity * 0.01
                    qty = int(risk_dollars / per_share_risk)
                    if qty <= 0:
                        continue
                    return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "short",
                                      symbol=bars[0].symbol, strategy="RoundNumber-50-150",
                                      risk_dollars=risk_dollars)
        # Test arrival at support (below)
        if abs(b.low - below) <= cfg.rn_proximity_dollar and b.close > below:
            if _is_doji(b) or _is_hammer(b):
                prev_vol = bars[i - 1].volume if i > 0 else 0
                if b.volume > prev_vol:
                    entry_idx = i + 1
                    entry_price = bars[entry_idx].open
                    stop = below - cfg.rn_stop_pad
                    target = above
                    if stop >= entry_price or target <= entry_price:
                        continue
                    per_share_risk = abs(entry_price - stop)
                    if per_share_risk <= 0:
                        continue
                    risk_dollars = equity * 0.01
                    qty = int(risk_dollars / per_share_risk)
                    if qty <= 0:
                        continue
                    return _walk_exit(bars, entry_idx, entry_price, stop, target, qty, "long",
                                      symbol=bars[0].symbol, strategy="RoundNumber-50-150",
                                      risk_dollars=risk_dollars)
    return None


# ---- Shared exit walker ----


def _walk_exit(
    bars: list[Bar],
    entry_idx: int,
    entry_price: float,
    stop: float,
    target: float,
    qty: int,
    direction: str,
    symbol: str,
    strategy: str,
    risk_dollars: float,
) -> TradeRec:
    """Walk forward from entry_idx; exit on stop / target / session_close."""
    exit_price: Optional[float] = None
    for j in range(entry_idx, len(bars)):
        b = bars[j]
        if direction == "long":
            if b.low <= stop:
                exit_price = stop
                break
            if b.high >= target:
                exit_price = target
                break
        else:
            if b.high >= stop:
                exit_price = stop
                break
            if b.low <= target:
                exit_price = target
                break
    if exit_price is None:
        exit_price = bars[-1].close
    if direction == "long":
        pnl = (exit_price - entry_price) * qty
    else:
        pnl = (entry_price - exit_price) * qty
    r = pnl / risk_dollars if risk_dollars > 0 else 0.0
    return TradeRec(
        symbol=symbol,
        session_date=bars[entry_idx].timestamp.date(),
        strategy=strategy,
        pnl=pnl,
        r=r,
        direction=direction,
    )


# =============================================================================
# DRIVER — Run a strategy across all (symbol, day) pairs in [start, end].
# =============================================================================


STRATEGIES = ["ORB-5min", "VWAP-MeanRev", "PDH-Fade", "PDH-Breakout", "RoundNumber-50-150"]


def run_strategy_window(
    strat: str,
    bars_all: dict[tuple[str, date], list[Bar]],
    start: date,
    end: date,
    cfg: StratParams,
    starting_equity: float = 100_000.0,
    fixed_dollar_sizing: bool = True,
) -> tuple[list[TradeRec], pd.Series]:
    """Run one strategy across [start, end]. Returns (trades, daily_pnl_series).

    fixed_dollar_sizing=True (default): risk is always 1% of starting_equity,
    NOT compounding. This makes quarter-concentration and Sharpe measurement
    fair on synthetic data, where exponential equity compounding pushes the
    later quarters to dominate by orders of magnitude.
    """
    keys = sorted(
        [k for k in bars_all if start <= k[1] <= end],
        key=lambda k: (k[1], k[0]),
    )
    trades: list[TradeRec] = []
    equity = starting_equity
    # Group keys by date so we can compute daily pnl
    daily_pnl: dict[date, float] = {}

    # Pre-compute PDH/PDL per (sym, day) for PDH strategies
    pdh_pdl: dict[tuple[str, date], tuple[float, float]] = {}
    if strat in ("PDH-Fade", "PDH-Breakout"):
        # Get prior session H/L for each (sym, date)
        by_sym: dict[str, list[tuple[date, list[Bar]]]] = {}
        for (sym, d), bars in bars_all.items():
            by_sym.setdefault(sym, []).append((d, bars))
        for sym, lst in by_sym.items():
            lst.sort(key=lambda x: x[0])
            for i in range(1, len(lst)):
                prev_bars = lst[i - 1][1]
                if not prev_bars:
                    continue
                ph = max(b.high for b in prev_bars)
                pl = min(b.low for b in prev_bars)
                pdh_pdl[(sym, lst[i][0])] = (ph, pl)

    for sym, d in keys:
        bars = bars_all.get((sym, d), [])
        if len(bars) < 10:
            continue
        trade: Optional[TradeRec] = None
        if strat == "ORB-5min":
            trade = simulate_orb(bars, cfg, equity)
        elif strat == "VWAP-MeanRev":
            trade = simulate_vwap_mr(bars, cfg, equity)
        elif strat == "PDH-Fade":
            pp = pdh_pdl.get((sym, d))
            if pp is None:
                continue
            trade = simulate_pdh_fade(bars, pp[0], pp[1], cfg, equity)
        elif strat == "PDH-Breakout":
            pp = pdh_pdl.get((sym, d))
            if pp is None:
                continue
            trade = simulate_pdh_break(bars, pp[0], pp[1], cfg, equity)
        elif strat == "RoundNumber-50-150":
            trade = simulate_round_number(bars, cfg, equity)
        if trade is not None:
            trades.append(trade)
            if not fixed_dollar_sizing:
                equity += trade.pnl
            daily_pnl[d] = daily_pnl.get(d, 0.0) + trade.pnl
    daily = pd.Series(daily_pnl).sort_index()
    return trades, daily


# =============================================================================
# WALK-FORWARD ENGINE
# =============================================================================


def walk_forward(
    strat: str,
    bars_all: dict[tuple[str, date], list[Bar]],
    cfg: StratParams,
    start: date = date(2020, 7, 1),  # first test month after 6-mo train (2020-01..06)
    end: date = date(2024, 12, 31),
) -> pd.DataFrame:
    """Run rolling 6-mo train / 1-mo test walk-forward across [start, end].

    For this synthetic data, "training" has no parameter fitting (we use the
    strategy's default config) — so train metrics are computed but used purely
    as a sanity check. The real validation is per-test-month Sharpe.
    """
    records = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        # Test window: 1 month starting at cur
        if cur.month == 12:
            next_month = date(cur.year + 1, 1, 1)
        else:
            next_month = date(cur.year, cur.month + 1, 1)
        test_end = next_month - timedelta(days=1)
        # Train: 6 months ending at cur - 1 day
        train_end = cur - timedelta(days=1)
        train_start_month = cur.month - 6
        train_start_year = cur.year
        while train_start_month <= 0:
            train_start_month += 12
            train_start_year -= 1
        train_start = date(train_start_year, train_start_month, 1)

        # Run test only (synthetic data — train is sanity)
        trades, daily = run_strategy_window(strat, bars_all, cur, test_end, cfg)
        n = len(trades)
        if n > 0 and len(daily) > 1:
            ret = daily / 100_000.0
            sharpe = float(ret.mean() / ret.std(ddof=1) * math.sqrt(252)) if ret.std(ddof=1) > 1e-12 else 0.0
            pnl = float(daily.sum())
            # Max drawdown on daily equity curve
            eq = daily.cumsum()
            running_max = eq.cummax()
            dd_pct = float(((eq - running_max) / 100_000.0).min())
        else:
            sharpe = 0.0
            pnl = 0.0
            dd_pct = 0.0

        records.append({
            "test_month": cur.isoformat()[:7],
            "test_start": cur,
            "test_end": test_end,
            "train_start": train_start,
            "train_end": train_end,
            "n_trades": n,
            "sharpe": sharpe,
            "pnl": pnl,
            "max_dd_pct": dd_pct,
        })
        cur = next_month
    return pd.DataFrame(records)


# =============================================================================
# REGIME SUB-TESTS — per (market, vol) bucket
# =============================================================================


def regime_breakdown(
    strat: str,
    bars_all: dict[tuple[str, date], list[Bar]],
    cfg: StratParams,
    regime_tag_df: pd.DataFrame,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Returns a DataFrame with columns: market, volregime, sharpe, n_trades, pnl."""
    trades, daily = run_strategy_window(strat, bars_all, start, end, cfg)
    if daily.empty:
        return pd.DataFrame(columns=["market", "volregime", "sharpe", "n_trades", "pnl"])
    # Join daily with regime tag
    daily_df = daily.reset_index().rename(columns={"index": "date", 0: "pnl"})
    daily_df.columns = ["date", "pnl"]
    daily_df["date"] = pd.to_datetime(daily_df["date"])
    rdf = regime_tag_df.copy()
    rdf["date"] = pd.to_datetime(rdf["date"])
    merged = daily_df.merge(rdf, on="date", how="left")
    rows = []
    for (mkt, vol), grp in merged.groupby(["market", "volregime"]):
        ret = grp["pnl"] / 100_000.0
        if len(ret) < 2 or ret.std(ddof=1) < 1e-12:
            sharpe = 0.0
        else:
            sharpe = float(ret.mean() / ret.std(ddof=1) * math.sqrt(252))
        rows.append({
            "market": mkt,
            "volregime": vol,
            "sharpe": sharpe,
            "n_days": len(ret),
            "pnl": float(grp["pnl"].sum()),
        })
    # Also count trades per regime bucket
    # (we'd need trade-by-trade tagging — approximate by daily aggregation)
    return pd.DataFrame(rows).sort_values(["market", "volregime"]).reset_index(drop=True)


# =============================================================================
# QUARTER CONCENTRATION
# =============================================================================


def quarter_concentration(trades: list[TradeRec]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([{"date": t.session_date, "pnl": t.pnl} for t in trades])
    df["date"] = pd.to_datetime(df["date"])
    df["quarter"] = df["date"].dt.to_period("Q")
    qpnl = df.groupby("quarter")["pnl"].sum().reset_index()
    total = qpnl["pnl"].sum()
    # Use absolute total for normalization (handles negative totals gracefully)
    denom = total if total > 0 else max(qpnl["pnl"].max(), 1e-9)
    qpnl["pct_of_total"] = qpnl["pnl"] / denom
    return qpnl.sort_values("pnl", ascending=False).reset_index(drop=True)


# =============================================================================
# BOOTSTRAP CONFIDENCE INTERVALS
# =============================================================================


def block_bootstrap_sharpe(
    daily_pnl: pd.Series,
    starting_equity: float = 100_000.0,
    n_samples: int = 1000,
    block_size: int = 20,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Block bootstrap of daily returns. Returns (point, lo_95, hi_95)."""
    if daily_pnl.empty:
        return 0.0, 0.0, 0.0
    rets = (daily_pnl / starting_equity).values
    if len(rets) < block_size * 2:
        block_size = max(2, len(rets) // 4)
    n = len(rets)
    rng = np.random.default_rng(seed)
    sharpes = []
    n_blocks = max(1, n // block_size)
    for _ in range(n_samples):
        # Sample n_blocks starting indices with replacement
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        sample = np.concatenate([rets[s:s + block_size] for s in starts])
        if sample.std(ddof=1) < 1e-12:
            continue
        s = sample.mean() / sample.std(ddof=1) * math.sqrt(252)
        sharpes.append(s)
    if not sharpes:
        return 0.0, 0.0, 0.0
    sharpes = np.array(sharpes)
    point = float(np.mean(sharpes))
    lo = float(np.percentile(sharpes, 2.5))
    hi = float(np.percentile(sharpes, 97.5))
    return point, lo, hi


# =============================================================================
# PARAMETER SENSITIVITY
# =============================================================================


def sensitivity_sweep(
    strat: str,
    bars_all: dict[tuple[str, date], list[Bar]],
    base_cfg: StratParams,
    param_name: str,
    base_value: float,
    points: tuple[float, ...] = (-0.2, -0.1, 0.0, 0.1, 0.2),
    start: date = date(2020, 7, 1),
    end: date = date(2024, 12, 31),
) -> pd.DataFrame:
    """Sweep `param_name` over ±20% of base_value; report Sharpe per setting."""
    rows = []
    for p in points:
        new_val = base_value * (1 + p)
        # For integer params (lookback, minutes), round
        from dataclasses import replace
        # Coerce int params
        int_params = {"orb_minutes", "vwap_lookback_bars", "fade_lookback"}
        if param_name in int_params:
            new_val = max(1, int(round(new_val)))
        cfg = replace(base_cfg, **{param_name: new_val})
        trades, daily = run_strategy_window(strat, bars_all, start, end, cfg)
        n = len(trades)
        if n > 0 and len(daily) > 1:
            ret = daily / 100_000.0
            sharpe = float(ret.mean() / ret.std(ddof=1) * math.sqrt(252)) if ret.std(ddof=1) > 1e-12 else 0.0
            pnl = float(daily.sum())
        else:
            sharpe = 0.0
            pnl = 0.0
        rows.append({
            "param": param_name,
            "delta_pct": p,
            "value": new_val,
            "sharpe": sharpe,
            "n_trades": n,
            "pnl": pnl,
        })
    return pd.DataFrame(rows)


# =============================================================================
# MAIN
# =============================================================================


def main():
    print("=" * 80)
    print("Wave 3 Agent K — Walk-Forward / Robustness Validation")
    print("=" * 80)
    print()

    start_date = date(2020, 1, 1)
    end_date = date(2024, 12, 31)

    # 1. Build universe
    print(f"[1/6] Generating regime-rich synthetic universe...")
    print(f"      8 symbols × ~1260 trading days × 5 yrs × quarterly regimes")
    bars_all, regime_df = make_universe(
        n_symbols=8,
        start_date=start_date,
        end_date=end_date,
        base_seed=7,
    )
    print(f"      {len(bars_all):,} symbol-day buckets generated")
    print()

    # 2. Classify regimes (bull/bear/chop × hi/med/lo vol)
    regime_tag_df = classify_regimes(regime_df)
    market_counts = regime_tag_df["market"].value_counts().to_dict()
    vol_counts = regime_tag_df["volregime"].value_counts().to_dict()
    print(f"[2/6] Regime classification:")
    print(f"      Market regime days: {market_counts}")
    print(f"      Vol regime days:    {vol_counts}")
    print()

    # 3. Walk-forward per strategy
    print(f"[3/6] Walk-forward per strategy (6-mo train, 1-mo test)...")
    cfg = StratParams()
    all_wf: dict[str, pd.DataFrame] = {}
    for strat in STRATEGIES:
        print(f"      Running {strat}...")
        wf = walk_forward(strat, bars_all, cfg)
        all_wf[strat] = wf
    print()

    # 4. Regime breakdown
    print(f"[4/6] Regime sub-tests...")
    all_regime: dict[str, pd.DataFrame] = {}
    for strat in STRATEGIES:
        rdf = regime_breakdown(strat, bars_all, cfg, regime_tag_df, start_date, end_date)
        all_regime[strat] = rdf
    print()

    # 5. Quarter concentration + bootstrap
    print(f"[5/6] Quarter concentration + bootstrap CI...")
    all_quarter: dict[str, pd.DataFrame] = {}
    all_boot: dict[str, tuple[float, float, float]] = {}
    all_full_trades: dict[str, list[TradeRec]] = {}
    all_daily: dict[str, pd.Series] = {}
    for strat in STRATEGIES:
        trades, daily = run_strategy_window(strat, bars_all, start_date, end_date, cfg)
        all_full_trades[strat] = trades
        all_daily[strat] = daily
        qdf = quarter_concentration(trades)
        all_quarter[strat] = qdf
        point, lo, hi = block_bootstrap_sharpe(daily)
        all_boot[strat] = (point, lo, hi)
    print()

    # 6. Sensitivity sweeps
    print(f"[6/6] Parameter sensitivity sweeps (±20%, 5 points)...")
    # Per-strategy parameter list (3-5 keys per directive)
    SENS_PARAMS = {
        "ORB-5min": [
            ("orb_minutes", 5.0),
            ("orb_vol_mult", 2.0),
            ("orb_min_breakout_pct", 0.0002),
            ("orb_proximity_pct", 0.001),
            ("orb_r_multiple", 2.0),
        ],
        "VWAP-MeanRev": [
            ("vwap_band_sigma", 2.0),
            ("vwap_proximity_pct", 0.003),
            ("vwap_lookback_bars", 2.0),
            ("vwap_stop_pad", 0.10),
            ("vwap_r_multiple", 1.5),
        ],
        "PDH-Fade": [
            ("fade_proximity_pct", 0.001),
            ("fade_lookback", 2.0),
            ("fade_stop_pad", 0.10),
            ("fade_r_multiple", 1.5),
        ],
        "PDH-Breakout": [
            ("brk_proximity_pct", 0.0005),
            ("brk_vol_mult", 2.0),
            ("brk_min_breakout_pct", 0.0002),
            ("brk_stop_pad", 0.02),
            ("brk_r_multiple", 2.0),
        ],
        "RoundNumber-50-150": [
            ("rn_increment", 5.0),
            ("rn_proximity_dollar", 0.25),
            ("rn_stop_pad", 0.10),
            ("rn_r_multiple", 2.0),
        ],
    }
    all_sens: dict[str, pd.DataFrame] = {}
    for strat, params in SENS_PARAMS.items():
        print(f"      Sweeping {strat}: {len(params)} params × 5 points...")
        frames = []
        for pname, pval in params:
            sw = sensitivity_sweep(strat, bars_all, cfg, pname, pval)
            frames.append(sw)
        all_sens[strat] = pd.concat(frames, ignore_index=True)
    print()

    # =========================================================================
    # WRITE OUTPUTS — JSON-serializable dict for the report writer
    # =========================================================================
    out_dir = Path("/Users/duffy/warrior_bot_v2/backtest/walk_forward_results")
    out_dir.mkdir(parents=True, exist_ok=True)

    def _safe_serialize(df: pd.DataFrame) -> list[dict]:
        # Convert dates/Periods to strings for JSON
        df2 = df.copy()
        for col in df2.columns:
            if df2[col].dtype == "object" or "datetime" in str(df2[col].dtype) or "period" in str(df2[col].dtype):
                df2[col] = df2[col].astype(str)
        return df2.to_dict(orient="records")

    summary = {}
    for strat in STRATEGIES:
        wf = all_wf[strat]
        win_months = int((wf["sharpe"] > 0).sum())
        total_months = len(wf)
        win_pct = win_months / total_months if total_months else 0.0

        qdf = all_quarter[strat]
        top_q_pct = float(qdf.iloc[0]["pct_of_total"]) if len(qdf) else 0.0

        point, lo, hi = all_boot[strat]

        sens_df = all_sens[strat]
        # Pass/fail per param: Sharpe stays > 1.0 within ±20%
        sens_pass = (sens_df.groupby("param")["sharpe"].min() > 1.0).all()
        # Cliff detection: drop > 0.5 Sharpe within ±10%
        sens_cliffs: list[str] = []
        for pname, grp in sens_df.groupby("param"):
            base = grp[grp["delta_pct"] == 0.0]["sharpe"].values
            within_10 = grp[grp["delta_pct"].abs() <= 0.1]["sharpe"]
            if len(base) and not within_10.empty:
                if (base[0] - within_10.min()) > 0.5:
                    sens_cliffs.append(pname)

        # Walk-forward win % pass: ≥ 70%
        wf_pass = win_pct >= 0.7
        conc_pass = top_q_pct <= 0.40
        boot_pass = lo > 0

        summary[strat] = {
            "wf_win_pct": win_pct,
            "wf_total_months": total_months,
            "wf_win_months": win_months,
            "wf_pass": wf_pass,
            "top_quarter_pct": top_q_pct,
            "conc_pass": conc_pass,
            "boot_sharpe_point": point,
            "boot_sharpe_lo": lo,
            "boot_sharpe_hi": hi,
            "boot_pass": boot_pass,
            "sens_pass": bool(sens_pass),
            "sens_cliffs": sens_cliffs,
            "overall_pass": wf_pass and conc_pass and boot_pass and bool(sens_pass),
        }

    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    for strat, s in summary.items():
        print(f"\n{strat}:")
        print(f"  Walk-forward win-month %: {s['wf_win_pct']:.1%} "
              f"({s['wf_win_months']}/{s['wf_total_months']}) "
              f"[{'PASS' if s['wf_pass'] else 'FAIL'} ≥70%]")
        print(f"  Top quarter concentration: {s['top_quarter_pct']:.1%} "
              f"[{'PASS' if s['conc_pass'] else 'FAIL'} ≤40%]")
        print(f"  Bootstrap Sharpe: {s['boot_sharpe_point']:.2f} "
              f"[{s['boot_sharpe_lo']:.2f}, {s['boot_sharpe_hi']:.2f}] "
              f"[{'PASS' if s['boot_pass'] else 'FAIL'} lo>0]")
        print(f"  Sensitivity (Sharpe >1.0 ±20%): "
              f"[{'PASS' if s['sens_pass'] else 'FAIL'}]"
              + (f"  cliffs: {s['sens_cliffs']}" if s['sens_cliffs'] else ""))
        print(f"  OVERALL: {'PASS' if s['overall_pass'] else 'FAIL'}")

    # Persist
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    for strat in STRATEGIES:
        safe_name = strat.replace("/", "_").replace(" ", "_")
        all_wf[strat].to_csv(out_dir / f"wf_{safe_name}.csv", index=False)
        all_regime[strat].to_csv(out_dir / f"regime_{safe_name}.csv", index=False)
        all_quarter[strat].to_csv(out_dir / f"quarter_{safe_name}.csv", index=False)
        all_sens[strat].to_csv(out_dir / f"sens_{safe_name}.csv", index=False)
        # Daily P&L too
        all_daily[strat].to_csv(out_dir / f"daily_{safe_name}.csv")
    print(f"\nAll results saved to {out_dir}/")
    return summary, all_wf, all_regime, all_quarter, all_sens, all_boot


if __name__ == "__main__":
    main()
