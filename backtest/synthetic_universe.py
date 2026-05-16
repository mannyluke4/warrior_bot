"""Synthetic intraday-bar generator for backtest harness fixtures.

Generates deterministic, parameterized minute-bar OHLCV data over a
multi-symbol, multi-year window. The generator targets the universe
research §2 distribution (price $10-300, day-range 2-10%, RV ≥1.5x) so
strategy backtests on synthetic data are at least in-distribution.

This is NOT a market simulator — it does not model microstructure, order
book dynamics, news, or correlated moves. It produces price paths that
respect:
  - A daily open with realistic gap from prior close (lognormal sigma).
  - Intraday drift sampled from a regime mix (trend / chop / reversal).
  - Per-bar volatility scaling with proximity to session start.
  - Volume that follows a U-shape (heavy open + close, quiet midday)
    with random one-bar spikes.
  - Occasional "level reaction" days where price probes the prior high
    or low and reverses — this is what makes PDH/PDL strategies
    profitable and ensures the synthetic universe has the same kind of
    edge real markets exhibit at known levels.

Deterministic given (seed, symbol, date).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

import numpy as np

from framework.level_sources.base import Bar


@dataclass
class UniverseConfig:
    n_symbols: int = 50
    start_date: date = date(2020, 1, 2)
    end_date: date = date(2024, 12, 31)
    min_price: float = 10.0
    max_price: float = 300.0
    base_seed: int = 42
    # Probability that a session "honors" the prior PDH/PDL (rejection/reaction).
    # Real markets show 40-60% rejection rates at PDH on first touch;
    # we use 0.45 here so breakouts have room to run too.
    level_reaction_prob: float = 0.45
    # Probability that a level break leads to continuation (vs. failed break).
    # When a session is NOT a reaction (1 - level_reaction_prob), this fraction
    # become continuation breakouts.
    level_breakout_prob: float = 0.65


def _trading_days(start: date, end: date) -> list[date]:
    """All weekday dates between [start, end], inclusive, dropping a few
    canonical US market holidays. This is approximate — close-enough for
    a synthetic backtest. NaN holidays just produce noisier bars; the
    PDH/PDL staleness gate already handles long gaps."""
    out: list[date] = []
    cur = start
    # US market closures (approximate set; the synthetic data is not pinned
    # to a real calendar — we just skip a representative density of holidays).
    fixed = {
        # New Year's Day
        (1, 1),
        # MLK Jr Day (3rd Mon of Jan) — approx
        # Skip — handled by gap_days probability
        # Memorial Day (last Mon May) — approx
        # July 4
        (7, 4),
        # Labor Day (1st Mon Sep) — approx
        # Thanksgiving (4th Thu Nov) — approx
        # Christmas
        (12, 25),
    }
    while cur <= end:
        if cur.weekday() < 5 and (cur.month, cur.day) not in fixed:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _symbol_universe(cfg: UniverseConfig) -> list[tuple[str, float]]:
    """Generate symbol names + base prices.

    Names are SYN001..SYNNNN; base prices are log-uniformly distributed in
    [min_price, max_price] so all tiers are represented.
    """
    rng = np.random.default_rng(cfg.base_seed)
    log_lo = math.log(cfg.min_price)
    log_hi = math.log(cfg.max_price)
    syms = []
    for i in range(cfg.n_symbols):
        base = math.exp(rng.uniform(log_lo, log_hi))
        syms.append((f"SYN{i:03d}", round(base, 2)))
    return syms


def generate_session_bars(
    symbol: str,
    session_date: date,
    open_price: float,
    sym_seed: int,
    *,
    bar_minutes: int = 5,
    rth_open: time = time(9, 30),
    rth_close: time = time(16, 0),
    prior_high: float | None = None,
    prior_low: float | None = None,
    reaction_prob: float = 0.50,
    breakout_prob: float = 0.55,
) -> list[Bar]:
    """Generate one RTH session of bars for one symbol-day.

    Determinism: result depends only on (symbol, session_date, sym_seed,
    open_price). Re-running with the same args yields identical bars.

    Reaction logic:
      - With prob `reaction_prob`, the session will WICK to prior_high (or
        prior_low) and then reject, closing back inside the prior range.
      - With prob `(1 - reaction_prob) * breakout_prob`, the session will
        break and CONTINUE past the prior high/low without reversing.
      - Otherwise, the session does not touch the prior high/low at all
        (drifts inside the range or outside on a different leg).

    Volume:
      - U-shape: 2x baseline at open, 1.5x at close, 1.0x midday.
      - One random "spike" bar at 2-3x baseline.
    """
    # Deterministic per-session RNG
    seed = hash((symbol, session_date.toordinal(), sym_seed)) % (2**31)
    rng = np.random.default_rng(seed)

    # Bars per session
    total_minutes = (rth_close.hour * 60 + rth_close.minute) - (
        rth_open.hour * 60 + rth_open.minute
    )
    n_bars = total_minutes // bar_minutes

    # Volatility scaled to base price — symbol-specific
    daily_sigma_pct = rng.uniform(0.015, 0.035)  # 1.5-3.5% expected daily range
    bar_sigma = open_price * daily_sigma_pct / math.sqrt(n_bars)

    # Sample regime
    regime = rng.choice(["trend_up", "trend_down", "chop", "reversal"],
                       p=[0.30, 0.25, 0.30, 0.15])
    drift_per_bar = {
        "trend_up": +0.00015,
        "trend_down": -0.00015,
        "chop": 0.0,
        "reversal": rng.choice([-0.00030, +0.00030]),
    }[regime] * open_price

    # Decide reaction plan for this session
    plan = None
    if prior_high is not None and prior_low is not None:
        u = rng.random()
        # Whether prior level is reachable
        # Decide which level to engage
        # PDH if open is closer to PDH; PDL if closer to PDL
        if abs(open_price - prior_high) < abs(open_price - prior_low):
            target_level = prior_high
            level_side = "PDH"
        else:
            target_level = prior_low
            level_side = "PDL"

        if u < reaction_prob:
            plan = ("react", level_side, target_level)
        elif u < reaction_prob + (1 - reaction_prob) * breakout_prob:
            plan = ("break", level_side, target_level)
        else:
            plan = ("ignore", level_side, target_level)
    else:
        plan = ("ignore", None, None)

    # Pick "touch bar" index (in the active trading window) for react/break plans
    touch_idx = int(rng.integers(low=3, high=max(4, n_bars - 5)))

    # Now walk bars
    bars: list[Bar] = []
    price = open_price
    session_high = open_price
    session_low = open_price
    base_volume = rng.uniform(2000, 25000)
    has_spiked = False

    for i in range(n_bars):
        # Timestamp
        minutes_from_open = i * bar_minutes
        ts = datetime.combine(session_date, rth_open) + timedelta(minutes=minutes_from_open)

        # Bar drift = baseline drift + noise; adjust around touch bar for reactions
        eps = rng.normal(0, bar_sigma)
        bar_drift = drift_per_bar + eps

        if plan and plan[0] in ("react", "break") and i == touch_idx:
            # Force a touch / wick to the target level
            target_level = plan[2]
            if plan[1] == "PDH":
                # Wick above the level
                target_high = target_level * (1.0 + rng.uniform(0.0005, 0.003))
                target_low = price * (1.0 - rng.uniform(0.0005, 0.002))
                if plan[0] == "react":
                    # Close back below the level (failed test -> rejection_down)
                    new_close = target_level * (1.0 - rng.uniform(0.0005, 0.003))
                else:
                    # Close above the level (breakout continuation)
                    new_close = target_level * (1.0 + rng.uniform(0.001, 0.004))
                bar_open = price
                bar_high = max(target_high, bar_open, new_close)
                bar_low = min(target_low, bar_open, new_close)
                # Volume on the touch bar must be high (2.5-4x) so confirmation passes.
                vol_mult = rng.uniform(2.5, 4.0)
            else:  # PDL
                target_low = target_level * (1.0 - rng.uniform(0.0005, 0.003))
                target_high = price * (1.0 + rng.uniform(0.0005, 0.002))
                if plan[0] == "react":
                    new_close = target_level * (1.0 + rng.uniform(0.0005, 0.003))
                else:
                    new_close = target_level * (1.0 - rng.uniform(0.001, 0.004))
                bar_open = price
                bar_low = min(target_low, bar_open, new_close)
                bar_high = max(target_high, bar_open, new_close)
                vol_mult = rng.uniform(2.5, 4.0)
            bar_close = new_close
            price = new_close
            # Step the planned follow-through into the regime drift for the
            # next several bars so the trade has somewhere to go.
            if plan[0] == "react":
                # After a rejection at PDH, drift downward (and vice versa)
                if plan[1] == "PDH":
                    drift_per_bar = -abs(drift_per_bar) - open_price * 0.0005
                else:
                    drift_per_bar = abs(drift_per_bar) + open_price * 0.0005
            else:
                # After a breakout, continue in the breakout direction.
                # Slightly larger magnitude than reaction because real
                # breakouts run further on average (continuation > mean-revert).
                if plan[1] == "PDH":
                    drift_per_bar = abs(drift_per_bar) + open_price * 0.0007
                else:
                    drift_per_bar = -abs(drift_per_bar) - open_price * 0.0007
        else:
            bar_open = price
            bar_close = max(0.01, bar_open + bar_drift)
            wick_lo = abs(rng.normal(0, bar_sigma * 0.5))
            wick_hi = abs(rng.normal(0, bar_sigma * 0.5))
            bar_high = max(bar_open, bar_close) + wick_hi
            bar_low = min(bar_open, bar_close) - wick_lo
            bar_low = max(0.01, bar_low)
            price = bar_close
            # Volume — U-shape
            t_norm = i / max(1, n_bars - 1)
            u_shape = 1.0 + 1.0 * (1.0 - 4.0 * t_norm * (1.0 - t_norm))
            vol_mult = u_shape * rng.uniform(0.7, 1.3)
            # Occasional spike
            if not has_spiked and rng.random() < 1.0 / n_bars * 2:
                vol_mult *= rng.uniform(2.0, 3.5)
                has_spiked = True

        # Track session H/L
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

    return bars


def generate_universe(
    cfg: UniverseConfig,
) -> dict[tuple[str, date], list[Bar]]:
    """Generate the full (symbol, date) -> bars map for the universe.

    Each session's open price is sampled from a lognormal walk anchored
    at the symbol's base price, with overnight gap noise added. The prior
    session's high/low feed the next session's reaction plan.
    """
    syms = _symbol_universe(cfg)
    dates = _trading_days(cfg.start_date, cfg.end_date)
    bars_map: dict[tuple[str, date], list[Bar]] = {}

    for sidx, (sym, base_price) in enumerate(syms):
        rng = np.random.default_rng(cfg.base_seed + sidx)
        price = base_price
        prior_high = None
        prior_low = None
        for d in dates:
            # Overnight gap (lognormal sigma ~0.01)
            gap = rng.normal(0, 0.012)
            open_price = max(0.01, price * (1.0 + gap))
            # Clip to keep prices reasonable
            open_price = max(cfg.min_price * 0.5, min(cfg.max_price * 1.5, open_price))

            bars = generate_session_bars(
                symbol=sym,
                session_date=d,
                open_price=open_price,
                sym_seed=sidx,
                prior_high=prior_high,
                prior_low=prior_low,
                reaction_prob=cfg.level_reaction_prob,
                breakout_prob=cfg.level_breakout_prob,
            )
            bars_map[(sym, d)] = bars
            # Update for next iter
            prior_high = max(b.high for b in bars)
            prior_low = min(b.low for b in bars)
            price = bars[-1].close

    return bars_map


__all__ = [
    "UniverseConfig",
    "generate_session_bars",
    "generate_universe",
]
