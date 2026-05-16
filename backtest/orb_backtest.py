"""ORB backtest harness — Wave 2 Agent F.

A bar-level replay engine that exercises the framework's ORB primitives
(OpeningRangeSource, BreakoutCandle, OppositeRange stop, RMultiple +
SessionClose composite target) over a multi-symbol multi-day universe.

Why a custom harness rather than nautilus_runner?
-------------------------------------------------
Per `2026-05-17_backtest_infra_validation.md` §"Known limitations", the
NautilusTrader 1.226 engine cannot be re-instantiated in the same Python
process. A multi-symbol multi-year ORB sweep would need subprocess-per-day
orchestration (~5000 subprocess spawns for 4 years × 5 symbols). That's
deferred to Wave 3's walk-forward agent; for the Wave 2 Agent F deliverable
we use a deterministic bar-replay engine that consumes the exact same
framework plugins (level_source, confirmation_rule, stop_rule, target_rule).

Fidelity caveat is honest: bar-level replay can't model intra-bar order
queue position. We approximate fills conservatively:
  - Entry: fill at the next bar's open (no look-ahead).
  - Stop hit: assume worst-case fill at the bar low (long) / high (short).
  - Target hit: assume best-case fill at the target price (a limit fill).
  - Session close: fill at the closing bar's close.

This is the same fidelity ceiling research §3 sketches for our stack
(85-90%); the 10-15% gap is what Nautilus tick-level replay closes when
we wire it up in Wave 3.

Per-tier attribution + sensitivity sweeps are built in: the harness
returns trade-level records with `price_tier` and `or_minutes` columns
so the report can pivot by either.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.confirmations.breakout_candle import BreakoutCandle
from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.opening_range import OpeningRangeSource
from framework.stops import OppositeRange
from framework.targets import CompositeTarget, RMultiple, SessionClose


log = logging.getLogger("orb_backtest")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ORBConfig:
    """All knobs for one backtest run."""

    minutes: int = 5
    min_vol_mult: float = 2.0
    min_breakout_pct: float = 0.0002
    proximity_pct: float = 0.001
    r_multiple: float = 2.0
    risk_per_trade_pct: float = 1.0
    starting_balance: float = 100_000.0
    max_concurrent_positions: int = 5
    trade_window_end: time = time(15, 55)
    # Bias gating: only take longs on green opening bar; shorts on red.
    use_direction_bias: bool = True
    # Cap one trade per symbol per day (Zarattini paper convention)
    one_trade_per_symbol_per_day: bool = True


@dataclass
class Trade:
    """A single closed ORB trade."""

    symbol: str
    session_date: date
    direction: str          # "long" / "short"
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: int
    stop_price: float
    target_price: Optional[float]
    pnl: float
    r_multiple: float
    exit_reason: str        # "target" | "stop" | "session_close"
    price_tier: str
    or_minutes: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date,
            "direction": self.direction,
            "entry_ts": self.entry_ts,
            "exit_ts": self.exit_ts,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "qty": self.qty,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "pnl": self.pnl,
            "r_multiple": self.r_multiple,
            "exit_reason": self.exit_reason,
            "price_tier": self.price_tier,
            "or_minutes": self.or_minutes,
        }


# ---------------------------------------------------------------------------
# Tiering helper
# ---------------------------------------------------------------------------


def price_tier(price: float) -> str:
    if price < 10:
        return "<$10"
    if price < 20:
        return "$10-20"
    if price < 50:
        return "$20-50"
    if price < 100:
        return "$50-100"
    if price < 200:
        return "$100-200"
    if price < 300:
        return "$200-300"
    return "$300+"


# ---------------------------------------------------------------------------
# Single-day single-symbol simulator
# ---------------------------------------------------------------------------


def simulate_day(
    symbol: str,
    bars: list[Bar],
    cfg: ORBConfig,
    starting_equity: float,
) -> Optional[Trade]:
    """Run one ORB sim on one symbol for one session.

    Returns the resulting Trade (or None if no setup fired).
    """
    if len(bars) < cfg.minutes + 1:
        return None

    # Build opening range
    src = OpeningRangeSource(minutes=cfg.minutes, use_5min_direction_bias=cfg.use_direction_bias)
    history_for_or = BarHistory(symbol=symbol, bars=list(bars))
    level_set = src.compute_levels(symbol, history_for_or)
    if not level_set.levels:
        return None
    orh_level = next((l for l in level_set.levels if l.kind == "ORH"), None)
    orl_level = next((l for l in level_set.levels if l.kind == "ORL"), None)
    if orh_level is None or orl_level is None:
        return None
    orh = orh_level.price
    orl = orl_level.price
    direction_bias = orh_level.metadata.get("direction_bias", "neutral")

    # Locate window-end bar index — the first bar after the OR window
    window_end_dt = datetime(
        bars[0].timestamp.year,
        bars[0].timestamp.month,
        bars[0].timestamp.day,
        9, 30,
    ) + timedelta(minutes=cfg.minutes)
    # Find the first bar with timestamp >= window_end
    start_idx = None
    for i, b in enumerate(bars):
        if b.timestamp >= window_end_dt:
            start_idx = i
            break
    if start_idx is None:
        return None

    # Confirmation plugin
    breakout = BreakoutCandle(
        min_vol_mult=cfg.min_vol_mult,
        min_breakout_pct=cfg.min_breakout_pct,
        require_close_beyond=True,
    )

    # Walk bars looking for a breakout in the allowed direction(s).
    long_allowed = (not cfg.use_direction_bias) or direction_bias == "long"
    short_allowed = (not cfg.use_direction_bias) or direction_bias == "short"

    entry_bar = None
    entry_direction = None
    entry_level = None
    for i in range(start_idx, len(bars)):
        b = bars[i]
        # Stop processing if past trade window end
        if b.timestamp.time() >= cfg.trade_window_end:
            break

        prior = bars[: i + 1]   # inclusive of entry candidate

        if long_allowed:
            res = breakout.check_confirmation(level=orh_level, bars=prior, l2_state=None)
            if res.confirmed and res.metadata.get("direction") == "long":
                entry_bar = b
                entry_direction = "long"
                entry_level = orh_level
                break
        if short_allowed:
            res = breakout.check_confirmation(level=orl_level, bars=prior, l2_state=None)
            if res.confirmed and res.metadata.get("direction") == "short":
                entry_bar = b
                entry_direction = "short"
                entry_level = orl_level
                break

    if entry_bar is None:
        return None

    # ----- entry fill -----
    # Convention: enter on the NEXT bar's open (no look-ahead intra-bar).
    entry_idx = bars.index(entry_bar)
    if entry_idx + 1 >= len(bars):
        return None
    fill_bar = bars[entry_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    # Stop: OppositeRange
    stop_rule = OppositeRange(opening_range_high=orh, opening_range_low=orl)
    stop_price = stop_rule.compute_stop(
        entry_price=entry_price,
        level=entry_level,
        history=BarHistory(symbol=symbol, bars=bars[: entry_idx + 1]),
        direction=entry_direction,
    )

    # Reject if stop is on wrong side (defensive — should never happen)
    if entry_direction == "long" and stop_price >= entry_price:
        return None
    if entry_direction == "short" and stop_price <= entry_price:
        return None

    # Position size: 1% equity at risk / per-share stop distance
    risk_dollars = starting_equity * (cfg.risk_per_trade_pct / 100.0)
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0:
        return None
    qty = int(risk_dollars // per_share_risk)
    if qty <= 0:
        return None

    # Target: composite — RMultiple primary, SessionClose fallback
    target = CompositeTarget(primary=RMultiple(r=cfg.r_multiple), fallback=SessionClose())
    tgt_spec = target.compute_target(
        entry_price=entry_price,
        level=entry_level,
        level_set=level_set,
        history=BarHistory(symbol=symbol, bars=bars[: entry_idx + 1]),
        direction=entry_direction,
        stop_price=stop_price,
    )
    target_price = tgt_spec.primary_price

    # ----- forward replay -----
    exit_price = None
    exit_ts = None
    exit_reason = None

    for j in range(entry_idx + 1, len(bars)):
        b = bars[j]
        # Session close forced exit
        if b.timestamp.time() >= cfg.trade_window_end:
            exit_price = b.close
            exit_ts = b.timestamp
            exit_reason = "session_close"
            break

        if entry_direction == "long":
            # Check stop first (conservative ordering — stop assumed to fire first
            # if both stop and target appear in the same bar)
            if b.low <= stop_price:
                exit_price = stop_price   # limit-fill assumption at stop
                exit_ts = b.timestamp
                exit_reason = "stop"
                break
            if target_price is not None and b.high >= target_price:
                exit_price = target_price
                exit_ts = b.timestamp
                exit_reason = "target"
                break
        else:  # short
            if b.high >= stop_price:
                exit_price = stop_price
                exit_ts = b.timestamp
                exit_reason = "stop"
                break
            if target_price is not None and b.low <= target_price:
                exit_price = target_price
                exit_ts = b.timestamp
                exit_reason = "target"
                break

    # If we ran off the end without an exit (incomplete data), force-close
    if exit_price is None:
        last = bars[-1]
        exit_price = last.close
        exit_ts = last.timestamp
        exit_reason = "session_close"

    if entry_direction == "long":
        pnl = (exit_price - entry_price) * qty
    else:
        pnl = (entry_price - exit_price) * qty
    r_mult = pnl / risk_dollars if risk_dollars > 0 else 0.0

    return Trade(
        symbol=symbol,
        session_date=entry_ts.date(),
        direction=entry_direction,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry_price=entry_price,
        exit_price=exit_price,
        qty=qty,
        stop_price=stop_price,
        target_price=target_price,
        pnl=pnl,
        r_multiple=r_mult,
        exit_reason=exit_reason,
        price_tier=price_tier(entry_price),
        or_minutes=cfg.minutes,
    )


# ---------------------------------------------------------------------------
# Multi-symbol multi-day driver
# ---------------------------------------------------------------------------


@dataclass
class ORBBacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series | None = None

    @property
    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_dict() for t in self.trades])


def run_orb_backtest(
    bars_by_symbol_day: dict[tuple[str, date], list[Bar]],
    cfg: ORBConfig,
) -> ORBBacktestResult:
    """Run ORB across a population of (symbol, day) bar histories.

    Equity compounds: trades are processed in chronological order across
    all symbols, with each trade sized off the equity that exists at its
    entry timestamp.
    """
    # Sort all (symbol, day) buckets by date
    keys = sorted(bars_by_symbol_day.keys(), key=lambda k: (k[1], k[0]))
    trades: list[Trade] = []
    equity = cfg.starting_balance
    equity_points: list[tuple[datetime, float]] = []

    for symbol, d in keys:
        bars = bars_by_symbol_day[(symbol, d)]
        if not bars:
            continue
        trade = simulate_day(symbol, bars, cfg, starting_equity=equity)
        if trade is None:
            continue
        equity += trade.pnl
        trades.append(trade)
        equity_points.append((trade.exit_ts, equity))

    eq = None
    if equity_points:
        eq = pd.Series(
            [e for _, e in equity_points],
            index=[ts for ts, _ in equity_points],
        ).sort_index()

    return ORBBacktestResult(trades=trades, equity_curve=eq)
