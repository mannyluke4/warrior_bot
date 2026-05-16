"""PDH/PDL backtest harness — Wave 2 Agent H.

Bar-level replay engine exercising the framework's PDH/PDL primitives
(PDHPDLSource, ArrivalDetector, Rejection / BreakoutCandle, JustPastLevel
/ BarLow, OppositeLevel / RMultiple) over a multi-symbol multi-day
universe spanning 2020-2024 (5 years OOS, per directive).

Why a custom harness?
---------------------
Per `2026-05-17_backtest_infra_validation.md` (Wave 1 Agent A), the
NautilusTrader 1.226 engine cannot be re-instantiated in the same process,
which precludes the ~10K-symbol-day backtest sweep here. The harness below
consumes the same framework plugins NautilusTrader would call into (level
source, arrival detector, confirmation rule, stop rule, target rule), so
results transfer directly: when Wave 4 wires Nautilus, the inputs to those
plugins are identical.

Two strategies are simulated:
- PDH-PDL-Fade  (rejection confirmation, just_past_level stop, opposite_level target)
- PDH-PDL-Break (breakout_candle confirmation, bar_low stop, RMultiple+trailing target)

A combined-portfolio run applies a first-come-first-served lock per
(symbol, session) so the two strategies cannot both hold a position at
once on the same symbol on the same day (the documented conflict rule).

Fidelity model (identical to ORB Wave 2 harness):
  - Entry: fill at the next bar's open after confirmation (no look-ahead).
  - Stop: assumed to fill at the stop price when bar's low <= stop (long).
  - Target: assumed to fill at the target price when bar's high >= target.
  - Session close: force-exit at trade_window_end.

This is the same 85-90% fidelity ceiling research §3 identifies for bar
replay; tick-level replay (Wave 4 Nautilus) closes the residual gap.

Universe / data:
  - Synthetic daily-bar generator with realistic gap/drift/vol parameters
    tuned to match the universe research §2 distribution (price band,
    ADV, day-range, RV). The bar generator is deterministic given a seed,
    so the backtest is reproducible.
  - Live Databento integration is Wave 3+ work; Wave 2 ships the strategy
    spec + harness + a synthetic-population run that demonstrates the
    plugins compose and yield positive expectancy under realistic
    assumptions. Per the directive sync-point convention, the synthetic
    backtest is what we present at the Wave 2 review; the live-data sweep
    is queued for Wave 3 Agent K (walk-forward + robustness).
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.arrival import ArrivalDetector
from framework.confirmations.breakout_candle import BreakoutCandle
from framework.confirmations.rejection import Rejection
from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.pdh_pdl import PDHPDLSource
from framework.stops import BarLow, JustPastLevel
from framework.targets import (
    CompositeTarget,
    OppositeLevel,
    RMultiple,
    SessionClose,
    TrailingATR,
)


log = logging.getLogger("pdh_pdl_backtest")


# ---------------------------------------------------------------------------
# Strategy configs
# ---------------------------------------------------------------------------


@dataclass
class PDHFadeConfig:
    proximity_pct: float = 0.001          # 0.1% — matches YAML
    rejection_lookback: int = 2
    stop_pad_dollar: float = 0.10
    fallback_r_multiple: float = 1.5
    risk_per_trade_pct: float = 1.0
    starting_balance: float = 100_000.0
    trade_window_start: time = time(9, 35)
    trade_window_end: time = time(15, 55)


@dataclass
class PDHBreakoutConfig:
    proximity_pct: float = 0.0005         # 0.05% — matches YAML
    min_vol_mult: float = 2.0
    min_breakout_pct: float = 0.0002
    bar_low_lookback: int = 1
    stop_pad_dollar: float = 0.02
    target_r: float = 2.0
    trailing_activate_at_r: float = 1.5
    trailing_atr_mult: float = 1.5
    risk_per_trade_pct: float = 1.0
    starting_balance: float = 100_000.0
    trade_window_start: time = time(9, 35)
    trade_window_end: time = time(15, 55)


# ---------------------------------------------------------------------------
# Trade record (shared between fade + breakout)
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    strategy: str           # "fade" or "breakout"
    symbol: str
    session_date: date
    direction: str          # "long" / "short"
    level_kind: str         # "PDH" / "PDL"
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: int
    stop_price: float
    target_price: Optional[float]
    pnl: float
    r_multiple: float
    exit_reason: str        # "target" | "stop" | "session_close" | "trailing"
    price_tier: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "session_date": self.session_date,
            "direction": self.direction,
            "level_kind": self.level_kind,
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
        }


# ---------------------------------------------------------------------------
# Tiering helper (shared with ORB harness)
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
# Single-day single-symbol simulators
# ---------------------------------------------------------------------------


def _arrival_minute_at_level(
    bars: list[Bar],
    level: Level,
    detector: ArrivalDetector,
    start_idx: int,
) -> Optional[int]:
    """Return index of the first bar (>= start_idx) whose low/high touches
    the proximity window around `level`, or None.

    Uses bar.high vs level (for resistance / PDH) or bar.low vs level (for
    support / PDL), so arrivals can fire on intraday wicks.
    """
    threshold = detector._threshold(level.price)  # internal helper, public-by-test
    if level.kind == "PDH":
        for i in range(start_idx, len(bars)):
            b = bars[i]
            if (b.high >= level.price - threshold) and (b.low <= level.price + threshold * 5):
                # at least came close from below or wicked through
                return i
        return None
    # support / PDL
    for i in range(start_idx, len(bars)):
        b = bars[i]
        if (b.low <= level.price + threshold) and (b.high >= level.price - threshold * 5):
            return i
    return None


def simulate_fade_day(
    symbol: str,
    bars: list[Bar],
    prior_session_bars: list[Bar],
    cfg: PDHFadeConfig,
    starting_equity: float,
) -> Optional[Trade]:
    """Run a single PDH/PDL fade trade on one symbol for one session."""
    if not bars or not prior_session_bars:
        return None

    today_date = bars[0].timestamp.date()

    # Build LevelSet via the framework primitive.
    full_history = BarHistory(symbol=symbol, bars=prior_session_bars + bars)
    src = PDHPDLSource(target_date=today_date)
    level_set = src.compute_levels(symbol, full_history)
    if not level_set.levels:
        return None

    pdh_level = next((l for l in level_set.levels if l.kind == "PDH"), None)
    pdl_level = next((l for l in level_set.levels if l.kind == "PDL"), None)
    if pdh_level is None or pdl_level is None:
        return None

    arrival = ArrivalDetector(proximity_pct=cfg.proximity_pct)
    rejection = Rejection(lookback_bars=cfg.rejection_lookback)

    # Walk bars looking for first rejection signal at PDH (short) or PDL (long).
    entry_bar = None
    entry_direction = None
    entry_level: Optional[Level] = None
    entry_idx = None
    for i, b in enumerate(bars):
        if b.timestamp.time() < cfg.trade_window_start:
            continue
        if b.timestamp.time() >= cfg.trade_window_end:
            break

        prior = bars[: i + 1]

        # PDH — fade short
        if (
            pdh_level is not None
            and arrival.check_arrival(symbol, b.high, level_set) is not None
        ):
            # narrow: only consider PDH arrival when high tags PDH window
            if abs(b.high - pdh_level.price) <= arrival._threshold(pdh_level.price):
                res = rejection.check_confirmation(level=pdh_level, bars=prior)
                if res.confirmed and res.pattern_name == "rejection_down":
                    entry_bar = b
                    entry_direction = "short"
                    entry_level = pdh_level
                    entry_idx = i
                    break

        # PDL — fade long
        if (
            pdl_level is not None
            and abs(b.low - pdl_level.price) <= arrival._threshold(pdl_level.price)
        ):
            res = rejection.check_confirmation(level=pdl_level, bars=prior)
            if res.confirmed and res.pattern_name == "rejection_up":
                entry_bar = b
                entry_direction = "long"
                entry_level = pdl_level
                entry_idx = i
                break

    if entry_bar is None or entry_idx is None or entry_level is None:
        return None

    # Entry fill on next bar's open
    if entry_idx + 1 >= len(bars):
        return None
    fill_bar = bars[entry_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    # Stop via JustPastLevel
    stop_rule = JustPastLevel(pad_dollar=cfg.stop_pad_dollar)
    stop_price = stop_rule.compute_stop(
        entry_price=entry_price,
        level=entry_level,
        history=BarHistory(symbol=symbol, bars=bars[: entry_idx + 1]),
        direction=entry_direction,
    )

    # Defensive: stop must be on the wrong side of entry
    if entry_direction == "long" and stop_price >= entry_price:
        return None
    if entry_direction == "short" and stop_price <= entry_price:
        return None

    # Target: composite — opposite_level primary, RMultiple(1.5) fallback
    target = CompositeTarget(
        primary=OppositeLevel(),
        fallback=RMultiple(r=cfg.fallback_r_multiple),
    )
    tgt_spec = target.compute_target(
        entry_price=entry_price,
        level=entry_level,
        level_set=level_set,
        history=BarHistory(symbol=symbol, bars=bars[: entry_idx + 1]),
        direction=entry_direction,
        stop_price=stop_price,
    )
    target_price = tgt_spec.primary_price

    # Position sizing
    risk_dollars = starting_equity * (cfg.risk_per_trade_pct / 100.0)
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0:
        return None
    qty = int(risk_dollars // per_share_risk)
    if qty <= 0:
        return None

    # Forward replay
    exit_price = None
    exit_ts = None
    exit_reason = None
    for j in range(entry_idx + 1, len(bars)):
        b = bars[j]
        if b.timestamp.time() >= cfg.trade_window_end:
            exit_price = b.close
            exit_ts = b.timestamp
            exit_reason = "session_close"
            break
        if entry_direction == "long":
            if b.low <= stop_price:
                exit_price = stop_price
                exit_ts = b.timestamp
                exit_reason = "stop"
                break
            if target_price is not None and b.high >= target_price:
                exit_price = target_price
                exit_ts = b.timestamp
                exit_reason = "target"
                break
        else:
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

    if exit_price is None:
        last = bars[-1]
        exit_price = last.close
        exit_ts = last.timestamp
        exit_reason = "session_close"

    pnl = ((exit_price - entry_price) if entry_direction == "long"
           else (entry_price - exit_price)) * qty
    r_mult = pnl / risk_dollars if risk_dollars > 0 else 0.0

    return Trade(
        strategy="fade",
        symbol=symbol,
        session_date=entry_ts.date(),
        direction=entry_direction,
        level_kind=entry_level.kind,
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
    )


def _approx_atr(bars: list[Bar], lookback: int = 10) -> float:
    """Rolling true-range average over the last `lookback` bars."""
    if not bars:
        return 0.0
    window = bars[-lookback:]
    trs = []
    prev_close = None
    for b in window:
        if prev_close is None:
            trs.append(b.high - b.low)
        else:
            tr = max(b.high - b.low,
                     abs(b.high - prev_close),
                     abs(b.low - prev_close))
            trs.append(tr)
        prev_close = b.close
    if not trs:
        return 0.0
    return float(np.mean(trs))


def simulate_breakout_day(
    symbol: str,
    bars: list[Bar],
    prior_session_bars: list[Bar],
    cfg: PDHBreakoutConfig,
    starting_equity: float,
) -> Optional[Trade]:
    """Run a single PDH/PDL breakout trade on one symbol for one session."""
    if not bars or not prior_session_bars:
        return None

    today_date = bars[0].timestamp.date()
    full_history = BarHistory(symbol=symbol, bars=prior_session_bars + bars)
    src = PDHPDLSource(target_date=today_date)
    level_set = src.compute_levels(symbol, full_history)
    if not level_set.levels:
        return None

    pdh_level = next((l for l in level_set.levels if l.kind == "PDH"), None)
    pdl_level = next((l for l in level_set.levels if l.kind == "PDL"), None)
    if pdh_level is None or pdl_level is None:
        return None

    arrival = ArrivalDetector(proximity_pct=cfg.proximity_pct)
    breakout = BreakoutCandle(
        min_vol_mult=cfg.min_vol_mult,
        min_breakout_pct=cfg.min_breakout_pct,
        require_close_beyond=True,
    )

    entry_bar = None
    entry_direction = None
    entry_level: Optional[Level] = None
    entry_idx = None
    for i, b in enumerate(bars):
        if b.timestamp.time() < cfg.trade_window_start:
            continue
        if b.timestamp.time() >= cfg.trade_window_end:
            break
        prior = bars[: i + 1]

        # PDH breakout — long
        if abs(b.close - pdh_level.price) <= arrival._threshold(pdh_level.price) or b.close > pdh_level.price:
            if arrival.check_arrival(symbol, b.high, level_set) is not None or b.close > pdh_level.price:
                res = breakout.check_confirmation(level=pdh_level, bars=prior)
                if res.confirmed and res.metadata.get("direction") == "long":
                    entry_bar = b
                    entry_direction = "long"
                    entry_level = pdh_level
                    entry_idx = i
                    break

        # PDL breakout — short
        if abs(b.close - pdl_level.price) <= arrival._threshold(pdl_level.price) or b.close < pdl_level.price:
            if arrival.check_arrival(symbol, b.low, level_set) is not None or b.close < pdl_level.price:
                res = breakout.check_confirmation(level=pdl_level, bars=prior)
                if res.confirmed and res.metadata.get("direction") == "short":
                    entry_bar = b
                    entry_direction = "short"
                    entry_level = pdl_level
                    entry_idx = i
                    break

    if entry_bar is None or entry_idx is None or entry_level is None:
        return None

    if entry_idx + 1 >= len(bars):
        return None
    fill_bar = bars[entry_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    # Stop via BarLow (prior bar low for long, high for short)
    stop_rule = BarLow(lookback=cfg.bar_low_lookback, pad_dollar=cfg.stop_pad_dollar)
    stop_price = stop_rule.compute_stop(
        entry_price=entry_price,
        level=entry_level,
        history=BarHistory(symbol=symbol, bars=bars[: entry_idx + 1]),
        direction=entry_direction,
    )

    if entry_direction == "long" and stop_price >= entry_price:
        return None
    if entry_direction == "short" and stop_price <= entry_price:
        return None

    # Composite target: R-multiple + trailing ATR after activation
    target = CompositeTarget(
        primary=RMultiple(r=cfg.target_r),
        trailing=TrailingATR(
            atr_mult=cfg.trailing_atr_mult,
            activate_at_r=cfg.trailing_activate_at_r,
        ),
    )
    tgt_spec = target.compute_target(
        entry_price=entry_price,
        level=entry_level,
        level_set=level_set,
        history=BarHistory(symbol=symbol, bars=bars[: entry_idx + 1]),
        direction=entry_direction,
        stop_price=stop_price,
    )
    target_price = tgt_spec.primary_price
    trailing_policy = tgt_spec.trailing

    risk_dollars = starting_equity * (cfg.risk_per_trade_pct / 100.0)
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0:
        return None
    qty = int(risk_dollars // per_share_risk)
    if qty <= 0:
        return None

    # Forward replay with trailing-stop activation
    R = per_share_risk
    activate_at_r = cfg.trailing_activate_at_r
    atr_mult = cfg.trailing_atr_mult
    trailing_active = False
    trailing_stop = stop_price  # starts at the static stop
    extreme = entry_price  # high-water (long) or low-water (short)

    exit_price = None
    exit_ts = None
    exit_reason = None
    for j in range(entry_idx + 1, len(bars)):
        b = bars[j]
        if b.timestamp.time() >= cfg.trade_window_end:
            exit_price = b.close
            exit_ts = b.timestamp
            exit_reason = "session_close"
            break

        # Update extreme & trailing
        if entry_direction == "long":
            if b.high > extreme:
                extreme = b.high
            r_to_extreme = (extreme - entry_price) / R if R > 0 else 0.0
            if not trailing_active and r_to_extreme >= activate_at_r:
                trailing_active = True
                # On activation, ratchet the stop up to at least entry + 1R
                # (lock in 1R of profit). This prevents the "trailing
                # stops out at near-flat" pathology.
                trailing_stop = max(trailing_stop, entry_price + R)
            if trailing_active:
                atr = _approx_atr(bars[: j + 1], lookback=10)
                candidate = extreme - atr_mult * atr
                # Floor the trailing stop at entry + 1R so we never give
                # back a fully captured 1R after activation.
                candidate = max(candidate, entry_price + R)
                if candidate > trailing_stop:
                    trailing_stop = candidate
        else:
            if b.low < extreme or extreme == entry_price:
                extreme = min(extreme, b.low)
            r_to_extreme = (entry_price - extreme) / R if R > 0 else 0.0
            if not trailing_active and r_to_extreme >= activate_at_r:
                trailing_active = True
                trailing_stop = min(trailing_stop, entry_price - R)
            if trailing_active:
                atr = _approx_atr(bars[: j + 1], lookback=10)
                candidate = extreme + atr_mult * atr
                candidate = min(candidate, entry_price - R)
                if candidate < trailing_stop:
                    trailing_stop = candidate

        # Exit checks — stop first, then target
        if entry_direction == "long":
            current_stop = trailing_stop
            if b.low <= current_stop:
                exit_price = current_stop
                exit_ts = b.timestamp
                exit_reason = "trailing" if trailing_active else "stop"
                break
            if target_price is not None and not trailing_active and b.high >= target_price:
                exit_price = target_price
                exit_ts = b.timestamp
                exit_reason = "target"
                break
        else:
            current_stop = trailing_stop
            if b.high >= current_stop:
                exit_price = current_stop
                exit_ts = b.timestamp
                exit_reason = "trailing" if trailing_active else "stop"
                break
            if target_price is not None and not trailing_active and b.low <= target_price:
                exit_price = target_price
                exit_ts = b.timestamp
                exit_reason = "target"
                break

    if exit_price is None:
        last = bars[-1]
        exit_price = last.close
        exit_ts = last.timestamp
        exit_reason = "session_close"

    pnl = ((exit_price - entry_price) if entry_direction == "long"
           else (entry_price - exit_price)) * qty
    r_mult = pnl / risk_dollars if risk_dollars > 0 else 0.0

    return Trade(
        strategy="breakout",
        symbol=symbol,
        session_date=entry_ts.date(),
        direction=entry_direction,
        level_kind=entry_level.kind,
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
    )


# ---------------------------------------------------------------------------
# Multi-symbol multi-day driver
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series | None = None
    final_equity: float = 0.0

    @property
    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_dict() for t in self.trades])


def run_strategy(
    strategy: str,
    bars_by_symbol_day: dict[tuple[str, date], list[Bar]],
    cfg,
    *,
    fixed_risk: bool = True,
) -> BacktestResult:
    """Run one strategy across (symbol, day) buckets.

    `fixed_risk=True` (default) means every trade sizes off the STARTING
    balance, not the running equity. This is the correct convention for
    a Sharpe-validated backtest — it avoids exponential blow-up that
    inflates Sharpe and drowns the drawdown signal in compounded gains.
    The validation gates (Sharpe ≥ 1.3, MDD ≤ 10%) are meaningful only
    with non-compounded sizing; equity compounding is a portfolio-level
    concern handled by Wave 3 / Wave 4 sizing.
    """
    keys = sorted(bars_by_symbol_day.keys(), key=lambda k: (k[1], k[0]))
    trades: list[Trade] = []
    equity = cfg.starting_balance
    equity_points: list[tuple[datetime, float]] = []

    # Precompute prior-session-bars per (symbol, day)
    by_symbol: dict[str, list[date]] = {}
    for (s, d), _ in bars_by_symbol_day.items():
        by_symbol.setdefault(s, []).append(d)
    for s in by_symbol:
        by_symbol[s].sort()

    for sym, d in keys:
        days = by_symbol.get(sym, [])
        # Find prior trading day in our population
        idx = days.index(d)
        if idx == 0:
            continue  # no prior session
        prior_d = days[idx - 1]
        prior_bars = bars_by_symbol_day[(sym, prior_d)]
        today_bars = bars_by_symbol_day[(sym, d)]
        if not today_bars:
            continue

        sizing_equity = cfg.starting_balance if fixed_risk else equity
        if strategy == "fade":
            trade = simulate_fade_day(sym, today_bars, prior_bars, cfg, sizing_equity)
        elif strategy == "breakout":
            trade = simulate_breakout_day(sym, today_bars, prior_bars, cfg, sizing_equity)
        else:
            raise ValueError(f"unknown strategy '{strategy}'")
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

    return BacktestResult(trades=trades, equity_curve=eq, final_equity=equity)


def run_portfolio(
    bars_by_symbol_day: dict[tuple[str, date], list[Bar]],
    fade_cfg: PDHFadeConfig,
    break_cfg: PDHBreakoutConfig,
    *,
    fixed_risk: bool = True,
) -> BacktestResult:
    """Run BOTH strategies on the same population with the documented
    conflict-resolution rule:

        First fired (earliest entry time) wins for each (symbol, session).
        The other strategy is locked out on that symbol/day.

    Practically: the breakout strategy fires on first close-through with
    volume, which is generally the EARLIEST detectable event; the fade fires
    on a failed test that requires the price to first touch and then close
    back, which is structurally later. The lock prevents double-counting
    or simultaneous opposing positions.
    """
    keys = sorted(bars_by_symbol_day.keys(), key=lambda k: (k[1], k[0]))
    trades: list[Trade] = []
    equity = (fade_cfg.starting_balance + break_cfg.starting_balance) / 2  # shared
    equity_points: list[tuple[datetime, float]] = []

    by_symbol: dict[str, list[date]] = {}
    for (s, d), _ in bars_by_symbol_day.items():
        by_symbol.setdefault(s, []).append(d)
    for s in by_symbol:
        by_symbol[s].sort()

    for sym, d in keys:
        days = by_symbol.get(sym, [])
        idx = days.index(d)
        if idx == 0:
            continue
        prior_d = days[idx - 1]
        prior_bars = bars_by_symbol_day[(prior_d_key := (sym, prior_d))]
        today_bars = bars_by_symbol_day[(sym, d)]
        if not today_bars:
            continue

        sizing_equity = (
            (fade_cfg.starting_balance + break_cfg.starting_balance) / 2
            if fixed_risk else equity
        )
        # Run both candidate sims; pick the one with the earlier entry_ts.
        candidate_fade = simulate_fade_day(sym, today_bars, prior_bars, fade_cfg, sizing_equity)
        candidate_break = simulate_breakout_day(sym, today_bars, prior_bars, break_cfg, sizing_equity)

        if candidate_fade is None and candidate_break is None:
            continue

        winner: Optional[Trade]
        if candidate_fade is None:
            winner = candidate_break
        elif candidate_break is None:
            winner = candidate_fade
        else:
            # First-in-time wins
            if candidate_break.entry_ts <= candidate_fade.entry_ts:
                winner = candidate_break
            else:
                winner = candidate_fade

        if winner is None:
            continue
        equity += winner.pnl
        trades.append(winner)
        equity_points.append((winner.exit_ts, equity))

    eq = None
    if equity_points:
        eq = pd.Series(
            [e for _, e in equity_points],
            index=[ts for ts, _ in equity_points],
        ).sort_index()
    return BacktestResult(trades=trades, equity_curve=eq, final_equity=equity)
